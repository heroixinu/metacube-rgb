from pathlib import Path
p=Path(__file__).parent/'driver/metacube_ambient.c'
s=p.read_text()
s=s.replace('#include <linux/kernel.h>', '#include <linux/kernel.h>\n#include <linux/hex.h>')
s=s.replace('#define FUNC_AMBIENT 0x0f', '#define FUNC_AMBIENT 0x0f\n#define FUNC_SYSTEM_MODE 0x08\n#define FUNC_BUTTON_LIGHT 0x19\n#define FUNC_FAN_RPM 0x0d')
s=s.replace('static bool allow_writes;\nmodule_param(allow_writes, bool, 0444);\nMODULE_PARM_DESC(allow_writes, "Opt in to ambient-light writes (default false)");','static bool allow_writes;\nmodule_param(allow_writes, bool, 0444);\nMODULE_PARM_DESC(allow_writes, "Opt in to ambient-light writes (default false)");\n\n/* Separate opt-in for thermal/performance-related and button LED writes. */\nstatic bool allow_platform_writes;\nmodule_param(allow_platform_writes, bool, 0444);\nMODULE_PARM_DESC(allow_platform_writes, "Opt in to OEM profile/button writes (default false)");')
s=s.replace('static int mc_wmi_call(struct metacube_ambient *ctx, u8 operation,\n                       const u8 *set_packet, u8 response[PACKET_SIZE])','static int mc_wmi_call_func(struct metacube_ambient *ctx, u8 operation,\n                       u8 function, const u8 *set_packet,\n                       u8 response[PACKET_SIZE])')
s=s.replace('    packet[3] = FUNC_AMBIENT;\n\n    status', '    packet[3] = function;\n\n    status')
s=s.replace('static bool mc_response_ok(const u8 response[PACKET_SIZE])','static int mc_wmi_call(struct metacube_ambient *ctx, u8 operation,\n                       const u8 *set_packet, u8 response[PACKET_SIZE])\n{\n    return mc_wmi_call_func(ctx, operation, FUNC_AMBIENT, set_packet, response);\n}\n\nstatic bool mc_response_ok_func(const u8 response[PACKET_SIZE], u8 function)\n{\n    return response[0] == 0 && response[1] == 0x80 &&\n           response[2] == 0 && response[3] == function;\n}\n\nstatic bool mc_response_ok(const u8 response[PACKET_SIZE])')
s=s.replace('    /* Return status 0x8000 (little-endian), function 0x0f00. */\n    return response[0] == 0 && response[1] == 0x80 &&\n           response[2] == 0 && response[3] == FUNC_AMBIENT;', '    return mc_response_ok_func(response, FUNC_AMBIENT);')
block=r'''
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
    int i, j, ret;

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

'''
s=s.replace('static struct attribute *metacube_ambient_attrs[] = {', block+'static struct attribute *metacube_ambient_attrs[] = {\n    &dev_attr_ambient_apply.attr,\n    &dev_attr_oem_system_mode.attr,\n    &dev_attr_oem_button_brightness.attr,\n    &dev_attr_oem_fan_rpm.attr,\n    &dev_attr_oem_gpu_mode.attr,\n    &dev_attr_oem_fn_lock.attr,\n    &dev_attr_oem_touchpad_lock.attr,\n    &dev_attr_oem_keyboard_mode.attr,\n    &dev_attr_oem_keyboard_brightness.attr,\n    &dev_attr_oem_ac_type.attr,\n    &dev_attr_oem_cpu_temperature.attr,')
s=s.replace('MODULE_VERSION("1.0.0")', 'MODULE_VERSION("2.0.0")')
s=s.replace('MODULE_DESCRIPTION("MetaCube ambient light WMI controller (verified readback)")', 'MODULE_DESCRIPTION("MetaCube OEM WMI controller: ambient RGB and gated OEM settings")')
p.write_text(s)
