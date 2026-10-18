/* Targeted macOS USB re-enumeration. No hub reset, power-cycle or seizure. */
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <IOKit/IOCFPlugIn.h>
#include <IOKit/usb/IOUSBLib.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint64_t number(io_service_t service, CFStringRef key) {
    CFTypeRef value = IORegistryEntryCreateCFProperty(service, key, NULL, 0);
    int64_t result = 0;
    if (value) {
        if (CFGetTypeID(value) == CFNumberGetTypeID())
            CFNumberGetValue((CFNumberRef)value, kCFNumberSInt64Type, &result);
        CFRelease(value);
    }
    return (uint64_t)result;
}

static uint64_t device_ecid(io_service_t service) {
    uint64_t ecid = number(service, CFSTR("UsbAppleDeviceECID"));
    if (ecid) return ecid;
    CFTypeRef value = IORegistryEntryCreateCFProperty(service, CFSTR("USB Serial Number"), NULL, 0);
    char serial[1024] = {0};
    if (value) {
        if (CFGetTypeID(value) == CFStringGetTypeID())
            CFStringGetCString(value, serial, sizeof(serial), kCFStringEncodingUTF8);
        CFRelease(value);
    }
    const char *field = strstr(serial, "ECID:");
    return field ? strtoull(field + 5, NULL, 16) : 0;
}

int main(int argc, char **argv) {
    if (argc != 3 || (strcmp(argv[1], "--probe") && strcmp(argv[1], "--reenumerate"))) {
        fprintf(stderr, "Usage: usb-reconnect --probe|--reenumerate ECID\n");
        return 2;
    }
    char *end = NULL;
    errno = 0;
    uint64_t expected = strtoull(argv[2], &end, 0);
    if (errno || !expected || !end || *end || argv[2][0] == '-') {
        fprintf(stderr, "A valid nonzero ECID is required.\n");
        return 2;
    }
    io_iterator_t iterator = IO_OBJECT_NULL;
    if (IOServiceGetMatchingServices(kIOMainPortDefault, IOServiceMatching("IOUSBHostDevice"), &iterator)) {
        fprintf(stderr, "Could not enumerate USB devices.\n");
        return 3;
    }
    io_service_t candidate = IO_OBJECT_NULL, service;
    unsigned matches = 0;
    while ((service = IOIteratorNext(iterator))) {
        uint64_t product = number(service, CFSTR("idProduct"));
        /* Only the iPhone DFU/recovery transport, never normal phones or hubs. */
        int recovery = product == 0x1227 || (product >= 0x1280 && product <= 0x1283);
        if (number(service, CFSTR("idVendor")) == 0x05ac && recovery && device_ecid(service) == expected) {
            matches++;
            if (!candidate) { candidate = service; IOObjectRetain(candidate); }
        }
        IOObjectRelease(service);
    }
    IOObjectRelease(iterator);
    if (matches != 1) {
        if (candidate) IOObjectRelease(candidate);
        fprintf(stderr, "Expected exactly one visible DFU/recovery device with the target ECID; found %u.\n", matches);
        return 3;
    }
    if (!strcmp(argv[1], "--probe")) {
        puts("Target is visible in the macOS USB registry. No reconnect was performed.");
        IOObjectRelease(candidate);
        return 0;
    }
    IOCFPlugInInterface **plugin = NULL;
    IOUSBDeviceInterface320 **device = NULL;
    SInt32 score = 0;
    IOReturn result = IOCreatePlugInInterfaceForService(candidate, kIOUSBDeviceUserClientTypeID,
        kIOCFPlugInInterfaceID, &plugin, &score);
    IOObjectRelease(candidate);
    if (result != kIOReturnSuccess || !plugin) {
        fprintf(stderr, "Could not access the target USB interface (0x%x).\n", result);
        return 4;
    }
    HRESULT queried = (*plugin)->QueryInterface(plugin,
        CFUUIDGetUUIDBytes(kIOUSBDeviceInterfaceID320), (LPVOID *)&device);
    (*plugin)->Release(plugin);
    if (queried || !device) {
        fprintf(stderr, "The target USB interface is unavailable.\n");
        return 4;
    }
    result = (*device)->USBDeviceOpen(device);
    if (result == kIOReturnSuccess) {
        result = (*device)->USBDeviceReEnumerate(device, 0);
        (*device)->USBDeviceClose(device);
    }
    (*device)->Release(device);
    if (result != kIOReturnSuccess) {
        fprintf(stderr, "USB re-enumeration request failed (0x%x).\n", result);
        return 4;
    }
    puts("Target USB re-enumeration requested. The device must be verified again.");
    return 0;
}
