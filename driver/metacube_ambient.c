// SPDX-License-Identifier: GPL-2.0-only
/*
 * Ambient light WMI controller for METAPHYUNI MetaCube (M11 Series-HPT).
 * Derived independently from OEM .NET IL and the public Bitland MIFS protocol.
 * Standalone WMI driver. Writes require allow_writes=1; no firmware calls on probe.
 */
#include <linux/acpi.h>
#include <linux/device.h>
#include <linux/dmi.h>
#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/hex.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/slab.h>
#include <linux/sysfs.h>
#include <linux/wmi.h>

#define MODULE_NAME "metacube_ambient"
#define CONTROL_GUID "B60BFB48-3E5B-49E4-A0E9-8CFFE1B3434B"
#define PACKET_SIZE 32
#define WMI_METHOD_ID 1
#define FUNC_AMBIENT 0x0f
#define FUNC_SYSTEM_MODE 0x08
#define FUNC_BUTTON_LIGHT 0x19
#define FUNC_FAN_RPM 0x0d
#define FUNC_AC_TYPE 0x13
#define OP_GET 0xfa
#define OP_SET 0xfb

/* Load with allow_writes=1 only after read-back validation. */
static bool allow_writes;
module_param(allow_writes, bool, 0444);
MODULE_PARM_DESC(allow_writes, "Opt in to ambient-light writes (default false)");

/* Separate opt-in for thermal/performance-related and button LED writes. */
static bool allow_platform_writes;
module_param(allow_platform_writes, bool, 0444);
MODULE_PARM_DESC(allow_platform_writes, "Opt in to OEM profile/button writes (default false)");

struct metacube_ambient {
    struct wmi_device *wdev;
    struct mutex lock;
};

/* Must be called with ctx->lock held. Does not change firmware state. */
static int mc_wmi_call_func(struct metacube_ambient *ctx, u8 operation,
                       u8 function, const u8 *set_packet,
                       u8 response[PACKET_SIZE])
{
    u8 packet[PACKET_SIZE] = { 0 };
    struct acpi_buffer in = {
        .length = sizeof(packet),
        .pointer = packet,
    };
    struct acpi_buffer out = {
        .length = ACPI_ALLOCATE_BUFFER,
        .pointer = NULL,
    };
    union acpi_object *obj;
    acpi_status status;
    int ret = 0;

    if (operation == OP_SET && set_packet)
        memcpy(packet, set_packet, sizeof(packet));
    packet[0] = 0;
    packet[1] = operation;
    packet[2] = 0;
    packet[3] = function;

    status = wmidev_evaluate_method(ctx->wdev, 0, WMI_METHOD_ID, &in, &out);
    if (ACPI_FAILURE(status)) {
        dev_warn(&ctx->wdev->dev, "WMI method failed: 0x%x\n", (unsigned int)status);
        kfree(out.pointer);
        return -EIO;
    }
    obj = out.pointer;
    if (!obj || obj->type != ACPI_TYPE_BUFFER ||
        obj->buffer.length < PACKET_SIZE || !obj->buffer.pointer) {
        dev_warn(&ctx->wdev->dev, "unexpected WMI response shape\n");
        ret = -EPROTO;
        goto done;
    }
    memcpy(response, obj->buffer.pointer, PACKET_SIZE);
done:
    kfree(out.pointer);
    return ret;
}

static int mc_wmi_call(struct metacube_ambient *ctx, u8 operation,
                       const u8 *set_packet, u8 response[PACKET_SIZE])
{
    return mc_wmi_call_func(ctx, operation, FUNC_AMBIENT, set_packet, response);
}

static bool mc_response_ok_func(const u8 response[PACKET_SIZE], u8 function)
{
    return response[0] == 0 && response[1] == 0x80 &&
           response[2] == 0 && response[3] == function;
}

static bool mc_response_ok(const u8 response[PACKET_SIZE])
{
    return mc_response_ok_func(response, FUNC_AMBIENT);
}

static int mc_read(struct metacube_ambient *ctx, u8 response[PACKET_SIZE])
{
    return mc_wmi_call(ctx, OP_GET, NULL, response);
}

/*
 * OEM Windows control center considers MiInterface invocation successful if
 * the WMI call did not throw; it does NOT require a 0x8000 reply on SET.
 * Some firmware revisions apply a SET, yet return a non-standard ACK (or an
 * ACPI method failure). Rather than suppressing an error, verify the intended
 * field via a fresh GET. Exactly one SET is issued per sysfs write.
 *
 * The caller holds ctx->lock and tells us which requested byte range changed.
 */
static int mc_write(struct metacube_ambient *ctx, u8 request[PACKET_SIZE],
                    size_t verify_offset, size_t verify_length)
{
    u8 set_response[PACKET_SIZE] = { 0 };
    u8 read_response[PACKET_SIZE] = { 0 };
    int set_ret, get_ret;

    if (!allow_writes)
        return -EPERM;
    if (!mc_response_ok(request))
        return -EPROTO;
    if (!verify_length || verify_offset < 4 ||
        verify_offset + verify_length > PACKET_SIZE)
        return -EINVAL;

    set_ret = mc_wmi_call(ctx, OP_SET, request, set_response);
    /* This MetaCube firmware replies with zero-filled SET ACKs.
     * That response is accepted only if the subsequent GET confirms the write.
     * Avoid flooding dmesg during normal LED changes.
     */
    if (!set_ret && !mc_response_ok(set_response) &&
        memchr_inv(set_response, 0, PACKET_SIZE))
        dev_warn(&ctx->wdev->dev,
                 "WMI SET replied %02x%02x%02x%02x (unexpected ACK); checking GET\n",
                 set_response[0], set_response[1],
                 set_response[2], set_response[3]);

    /* The new GET is authoritative for the selected setting. */
    get_ret = mc_read(ctx, read_response);
    if (get_ret) {
        dev_warn(&ctx->wdev->dev,
                 "WMI SET verification GET failed (%d), SET result was %d\n",
                 get_ret, set_ret);
        return set_ret ? set_ret : get_ret;
    }
    if (!mc_response_ok(read_response))
        return -EPROTO;
    if (memcmp(request + verify_offset,
               read_response + verify_offset, verify_length)) {
        dev_warn(&ctx->wdev->dev,
                 "WMI SET readback mismatch at offset %zu length %zu (SET result %d)\n",
                 verify_offset, verify_length, set_ret);
        return set_ret ? set_ret : -EIO;
    }

    if (set_ret)
        dev_warn(&ctx->wdev->dev,
                 "WMI SET returned %d but GET confirmed requested field; accepting readback\n",
                 set_ret);
    return 0;
}
static ssize_t ambient_raw_show(struct device *dev,
                                struct device_attribute *attr, char *buf)
{
    struct metacube_ambient *ctx = dev_get_drvdata(dev);
    u8 response[PACKET_SIZE];
    int ret;

    mutex_lock(&ctx->lock);
    ret = mc_read(ctx, response);
    mutex_unlock(&ctx->lock);
    if (ret)
        return ret;
    return sysfs_emit(buf, "%*phN\n", PACKET_SIZE, response);
}
static DEVICE_ATTR_RO(ambient_raw);

static ssize_t ambient_mode_show(struct device *dev,
                                 struct device_attribute *attr, char *buf)
{
    struct metacube_ambient *ctx = dev_get_drvdata(dev);
    u8 response[PACKET_SIZE];
    int ret;

    mutex_lock(&ctx->lock);
    ret = mc_read(ctx, response);
    mutex_unlock(&ctx->lock);
    if (ret)
        return ret;
    if (!mc_response_ok(response))
        return -EPROTO;
    return sysfs_emit(buf, "%u\n", response[4]);
}

static ssize_t ambient_mode_store(struct device *dev,
                                  struct device_attribute *attr,
                                  const char *buf, size_t count)
{
    struct metacube_ambient *ctx = dev_get_drvdata(dev);
    unsigned int mode;
    u8 packet[PACKET_SIZE];
    int ret;

    if (!allow_writes)
        return -EPERM;
    ret = kstrtouint(buf, 0, &mode);
    if (ret)
        return ret;
    if (mode < 2 || mode > 5)
        return -EINVAL; /* 2 breath, 3 steady, 4 spin, 5 off */

    mutex_lock(&ctx->lock);
    ret = mc_read(ctx, packet);
    if (!ret) {
        packet[4] = (u8)mode;
        ret = mc_write(ctx, packet, 4, 1);
    }
    mutex_unlock(&ctx->lock);
    return ret ? ret : count;
}
static DEVICE_ATTR_RW(ambient_mode);

static ssize_t ambient_brightness_show(struct device *dev,
                                       struct device_attribute *attr, char *buf)
{
    struct metacube_ambient *ctx = dev_get_drvdata(dev);
    u8 response[PACKET_SIZE];
    int ret;

    mutex_lock(&ctx->lock);
    ret = mc_read(ctx, response);
    mutex_unlock(&ctx->lock);
    if (ret)
        return ret;
    if (!mc_response_ok(response))
        return -EPROTO;
    return sysfs_emit(buf, "%u\n", response[24]);
}

static ssize_t ambient_brightness_store(struct device *dev,
                                        struct device_attribute *attr,
                                        const char *buf, size_t count)
{
    struct metacube_ambient *ctx = dev_get_drvdata(dev);
    unsigned int brightness;
    u8 packet[PACKET_SIZE];
    int ret;

    if (!allow_writes)
        return -EPERM;
    ret = kstrtouint(buf, 0, &brightness);
    if (ret)
        return ret;
    if (brightness > 255)
        return -EINVAL;
    mutex_lock(&ctx->lock);
    ret = mc_read(ctx, packet);
    if (!ret) {
        packet[24] = (u8)brightness;
        ret = mc_write(ctx, packet, 24, 1);
    }
    mutex_unlock(&ctx->lock);
    return ret ? ret : count;
}
static DEVICE_ATTR_RW(ambient_brightness);

static ssize_t ambient_color_show(struct device *dev,
                                  struct device_attribute *attr, char *buf)
{
    struct metacube_ambient *ctx = dev_get_drvdata(dev);
    u8 response[PACKET_SIZE];
    int ret;

    mutex_lock(&ctx->lock);
    ret = mc_read(ctx, response);
    mutex_unlock(&ctx->lock);
    if (ret)
        return ret;
    if (!mc_response_ok(response))
        return -EPROTO;
    return sysfs_emit(buf, "%02X%02X%02X (count=%u)\n",
                      response[6], response[7], response[8], response[5]);
}

static ssize_t ambient_color_store(struct device *dev,
                                   struct device_attribute *attr,
                                   const char *buf, size_t count)
{
    struct metacube_ambient *ctx = dev_get_drvdata(dev);
    unsigned int rgb;
    const char *p = buf;
    u8 packet[PACKET_SIZE];
    int ret;

    if (!allow_writes)
        return -EPERM;
    if (*p == '#')
        p++;
    ret = kstrtouint(p, 16, &rgb);
    if (ret)
        return ret;
    if (rgb > 0xffffff)
        return -EINVAL;
    mutex_lock(&ctx->lock);
    ret = mc_read(ctx, packet);
    if (!ret) {
        packet[5] = 1;
        packet[6] = (rgb >> 16) & 0xff;
        packet[7] = (rgb >> 8) & 0xff;
        packet[8] = rgb & 0xff;
        memset(packet + 9, 0, 15); /* remaining 5 RGB color slots */
        ret = mc_write(ctx, packet, 5, 4);
    }
    mutex_unlock(&ctx->lock);
    return ret ? ret : count;
}
static DEVICE_ATTR_RW(ambient_color);


/*
 * Structured lighting: one firmware SET for all original OEM lighting
 * fields. Syntax: MODE BRIGHTNESS SPEED DIRECTION CYCLE TRANSITION RGB[,RGB...]
 * 1..6 colors, six-digit RGB only. All other command bytes come from the
 * latest GET rather than an uncontrolled userspace buffer.
 */
static ssize_t ambient_apply_store(struct device *dev,
                                   struct device_attribute *attr,
                                   const char *buf, size_t count)
{
    struct metacube_ambient *ctx = dev_get_drvdata(dev);
    char *input, *cursor, *parts[7], *rgbcursor, *token;
    u8 packet[PACKET_SIZE];
    unsigned int nums[6], colors = 0;
    int i, ret;

    if (!allow_writes)
        return -EPERM;
    if (count < 16 || count > 160)
        return -EINVAL;
    input = kstrndup(buf, count, GFP_KERNEL);
    if (!input)
        return -ENOMEM;
    cursor = strim(input);
    for (i = 0; i < 7; i++) {
        parts[i] = strsep(&cursor, " \t\n");
        if (!parts[i] || !*parts[i]) {
            ret = -EINVAL;
            goto out;
        }
    }
    if (cursor && *cursor) {
        ret = -EINVAL;
        goto out;
    }
    for (i = 0; i < 6; i++) {
        ret = kstrtouint(parts[i], 10, &nums[i]);
        if (ret)
            goto out;
    }
    if (nums[0] < 2 || nums[0] > 5 || nums[1] > 255 ||
        nums[2] > 255 || nums[3] > 1 || nums[4] > 11 || nums[5] > 1) {
        ret = -EINVAL;
        goto out;
    }

    mutex_lock(&ctx->lock);
    ret = mc_read(ctx, packet);
    if (ret)
        goto unlock;
    if (!mc_response_ok(packet)) {
        ret = -EPROTO;
        goto unlock;
    }
    packet[4] = nums[0];
    memset(packet + 6, 0, 18);
    rgbcursor = parts[6];
    while ((token = strsep(&rgbcursor, ",")) != NULL) {
        if (!*token || strlen(token) != 6 || colors >= 6 ||
            hex2bin(packet + 6 + colors * 3, token, 3)) {
            ret = -EINVAL;
            goto unlock;
        }
        colors++;
    }
    if (!colors) {
        ret = -EINVAL;
        goto unlock;
    }
    packet[5] = colors;
    packet[24] = nums[1];
    packet[25] = nums[2];
    packet[26] = nums[3];
    packet[27] = nums[4];
    packet[28] = nums[5];
    /* Validate only OEM-controlled fields, not the reserved suffix. */
    ret = mc_write(ctx, packet, 4, 25);
unlock:
    mutex_unlock(&ctx->lock);
out:
    kfree(input);
    return ret ? ret : count;
}
static DEVICE_ATTR_WO(ambient_apply);

static int mc_read_oem(struct metacube_ambient *ctx, u8 function,
                       u8 response[PACKET_SIZE])
{
    int ret = mc_wmi_call_func(ctx, OP_GET, function, NULL, response);
    if (ret)
        return ret;
    if (!mc_response_ok_func(response, function))
        return -EOPNOTSUPP;
    return 0;
}

/* OEM function catalog read-only diagnostics. These are never called on probe. */
#define OEM_U8_SHOW(name, function)                                   \
static ssize_t name##_show(struct device *dev,                         \
                           struct device_attribute *attr, char *buf)   \
{                                                                        \
    struct metacube_ambient *ctx = dev_get_drvdata(dev);                \
    u8 result[PACKET_SIZE];                                             \
    int ret;                                                            \
    mutex_lock(&ctx->lock);                                             \
    ret = mc_read_oem(ctx, function, result);                            \
    mutex_unlock(&ctx->lock);                                           \
    if (ret)                                                            \
        return ret;                                                     \
    return sysfs_emit(buf, "%u\n", result[4]);                         \
}                                                                        \
static DEVICE_ATTR_RO(name)

OEM_U8_SHOW(oem_gpu_mode, 0x09);
OEM_U8_SHOW(oem_fn_lock, 0x0b);
OEM_U8_SHOW(oem_touchpad_lock, 0x0c);
OEM_U8_SHOW(oem_keyboard_mode, 0x10);
OEM_U8_SHOW(oem_keyboard_brightness, 0x12);
OEM_U8_SHOW(oem_ac_type, 0x13);
OEM_U8_SHOW(oem_cpu_temperature, 0x16);

static ssize_t oem_fan_rpm_show(struct device *dev,
                                struct device_attribute *attr, char *buf)
{
    struct metacube_ambient *ctx = dev_get_drvdata(dev);
    u8 output[PACKET_SIZE];
    int ret;
    mutex_lock(&ctx->lock);
    ret = mc_read_oem(ctx, FUNC_FAN_RPM, output);
    mutex_unlock(&ctx->lock);
    if (ret)
        return ret;
    return sysfs_emit(buf, "%u %u\n",
                      (unsigned int)output[4] | ((unsigned int)output[5] << 8),
                      (unsigned int)output[6] | ((unsigned int)output[7] << 8));
}
static DEVICE_ATTR_RO(oem_fan_rpm);

/* These two OEM controls require a distinct, explicit platform opt-in. */
static int mc_set_oem_scalar(struct metacube_ambient *ctx, u8 function, u8 val)
{
    u8 packet[PACKET_SIZE] = { 0 }, output[PACKET_SIZE] = { 0 };
    int set_ret, get_ret;
    if (!allow_writes || !allow_platform_writes)
        return -EPERM;
    packet[4] = val;
    set_ret = mc_wmi_call_func(ctx, OP_SET, function, packet, output);
    get_ret = mc_read_oem(ctx, function, output);
    if (get_ret)
        return set_ret ? set_ret : get_ret;
    if (output[4] != val)
        return set_ret ? set_ret : -EIO;
    return 0;
}

static ssize_t oem_system_mode_show(struct device *dev,
                                    struct device_attribute *attr, char *buf)
{
    struct metacube_ambient *ctx = dev_get_drvdata(dev);
    u8 result[PACKET_SIZE];
    int ret;
    mutex_lock(&ctx->lock);
    ret = mc_read_oem(ctx, FUNC_SYSTEM_MODE, result);
    mutex_unlock(&ctx->lock);
    if (ret)
        return ret;
    return sysfs_emit(buf, "%u\n", result[4]);
}
static ssize_t oem_system_mode_store(struct device *dev,
                                     struct device_attribute *attr,
                                     const char *buf, size_t count)
{
    struct metacube_ambient *ctx = dev_get_drvdata(dev);
    unsigned int val;
    int ret;
    if (kstrtouint(buf, 10, &val) || val > 2)
        return -EINVAL;
    if (!allow_platform_writes || !allow_writes)
        return -EPERM;
    mutex_lock(&ctx->lock);
    /* The Windows OEM UI restricts Turbo based on AC adapter type.
     * For safety, only allow Turbo when the firmware positively reports
     * circular-jack power (2). Unrecognized/USB-C power fails closed.
     */
    if (val == 0) {
        u8 ac[PACKET_SIZE];
        ret = mc_read_oem(ctx, FUNC_AC_TYPE, ac);
        if (ret || ac[4] != 2) {
            mutex_unlock(&ctx->lock);
            return -EOPNOTSUPP;
        }
    }
    ret = mc_set_oem_scalar(ctx, FUNC_SYSTEM_MODE, val);
    mutex_unlock(&ctx->lock);
    return ret ? ret : count;
}
static DEVICE_ATTR_RW(oem_system_mode);

static ssize_t oem_button_brightness_show(struct device *dev,
                                         struct device_attribute *attr, char *buf)
{
    struct metacube_ambient *ctx = dev_get_drvdata(dev);
    u8 result[PACKET_SIZE];
    int ret;
    mutex_lock(&ctx->lock);
    ret = mc_read_oem(ctx, FUNC_BUTTON_LIGHT, result);
    mutex_unlock(&ctx->lock);
    if (ret)
        return ret;
    return sysfs_emit(buf, "%u\n", result[4]);
}
static ssize_t oem_button_brightness_store(struct device *dev,
                                          struct device_attribute *attr,
                                          const char *buf, size_t count)
{
    struct metacube_ambient *ctx = dev_get_drvdata(dev);
    unsigned int val;
    int ret;
    if (kstrtouint(buf, 10, &val) || val > 3)
        return -EINVAL;
    if (!allow_platform_writes || !allow_writes)
        return -EPERM;
    mutex_lock(&ctx->lock);
    ret = mc_set_oem_scalar(ctx, FUNC_BUTTON_LIGHT, val);
    mutex_unlock(&ctx->lock);
    return ret ? ret : count;
}
static DEVICE_ATTR_RW(oem_button_brightness);

static struct attribute *metacube_ambient_attrs[] = {
    &dev_attr_ambient_apply.attr,
    &dev_attr_oem_system_mode.attr,
    &dev_attr_oem_button_brightness.attr,
    &dev_attr_oem_fan_rpm.attr,
    &dev_attr_oem_gpu_mode.attr,
    &dev_attr_oem_fn_lock.attr,
    &dev_attr_oem_touchpad_lock.attr,
    &dev_attr_oem_keyboard_mode.attr,
    &dev_attr_oem_keyboard_brightness.attr,
    &dev_attr_oem_ac_type.attr,
    &dev_attr_oem_cpu_temperature.attr,
    &dev_attr_ambient_raw.attr,
    &dev_attr_ambient_mode.attr,
    &dev_attr_ambient_brightness.attr,
    &dev_attr_ambient_color.attr,
    NULL,
};
ATTRIBUTE_GROUPS(metacube_ambient);

static int metacube_ambient_probe(struct wmi_device *wdev, const void *context)
{
    struct metacube_ambient *ctx;

    if (!dmi_match(DMI_SYS_VENDOR, "METAPHYUNI") ||
        !dmi_match(DMI_PRODUCT_NAME, "MetaCube") ||
        !dmi_match(DMI_BOARD_NAME, "M11 Series-HPT"))
        return -ENODEV;

    ctx = devm_kzalloc(&wdev->dev, sizeof(*ctx), GFP_KERNEL);
    if (!ctx)
        return -ENOMEM;
    ctx->wdev = wdev;
    mutex_init(&ctx->lock);
    dev_set_drvdata(&wdev->dev, ctx);
    dev_info(&wdev->dev, "MetaCube ambient WMI ready (write access %s)\n",
             allow_writes ? "enabled" : "disabled");
    return 0;
}

static const struct wmi_device_id metacube_ambient_ids[] = {
    { .guid_string = CONTROL_GUID },
    { }
};
MODULE_DEVICE_TABLE(wmi, metacube_ambient_ids);

static struct wmi_driver metacube_ambient_driver = {
    .driver = {
        .name = MODULE_NAME,
        .dev_groups = metacube_ambient_groups,
    },
    .id_table = metacube_ambient_ids,
    .probe = metacube_ambient_probe,
};
module_wmi_driver(metacube_ambient_driver);

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("MetaCube OEM WMI controller: ambient RGB and gated OEM settings");
MODULE_VERSION("2.1.0");
MODULE_AUTHOR("OpenAI ChatGPT (reverse engineering aid)");
