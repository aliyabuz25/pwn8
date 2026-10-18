"""Read SpringBoard's actual icon state without changing its layout."""
import ctypes as C
import plistlib
from .boot_assets import KIT


def contains_cydia(value):
    if isinstance(value, list):
        return any(contains_cydia(item) for item in value)
    if isinstance(value, dict):
        return value.get('displayIdentifier') == 'com.saurik.Cydia' or any(
            contains_cydia(item) for item in value.values() if isinstance(item,(list,dict)))
    return value == 'com.saurik.Cydia'


def read_icons(udid):
    ptr = C.c_void_p
    plist = C.CDLL(str(KIT/'bin/macos/lib/libplist-2.0.12.dylib'), mode=C.RTLD_GLOBAL)
    mobile = C.CDLL(str(KIT/'bin/macos/lib/libimobiledevice-1.0.6.dylib'))
    for name,args in [('idevice_new',[C.POINTER(ptr),C.c_char_p]),('idevice_free',[ptr]),
        ('sbservices_client_start_service',[ptr,C.POINTER(ptr),C.c_char_p]),
        ('sbservices_client_free',[ptr]),('sbservices_get_icon_state',[ptr,C.POINTER(ptr),C.c_char_p])]:
        function=getattr(mobile,name);function.argtypes=args;function.restype=C.c_int
    plist.plist_to_xml.argtypes=[ptr,C.POINTER(ptr),C.POINTER(C.c_uint32)]
    plist.plist_free.argtypes=[ptr];plist.plist_mem_free.argtypes=[ptr]
    device=ptr();client=ptr();node=ptr();xml=ptr()
    def check(code):
        if code:raise RuntimeError('SpringBoard service returned error '+str(code))
    try:
        check(mobile.idevice_new(C.byref(device),udid.encode()))
        check(mobile.sbservices_client_start_service(device,C.byref(client),b'remed1st'))
        check(mobile.sbservices_get_icon_state(client,C.byref(node),b'2'))
        size=C.c_uint32()
        plist.plist_to_xml(node,C.byref(xml),C.byref(size))
        if not xml.value:raise RuntimeError('SpringBoard returned no icon state.')
        return plistlib.loads(C.string_at(xml,size.value))
    finally:
        if xml:plist.plist_mem_free(xml)
        if node:plist.plist_free(node)
        if client:mobile.sbservices_client_free(client)
        if device:mobile.idevice_free(device)


if __name__=='__main__':
    import sys
    try:
        visible=contains_cydia(read_icons(sys.argv[1]))
        print('Cydia icon verified.' if visible else 'Cydia icon not found.')
        raise SystemExit(0 if visible else 1)
    except Exception as error:
        print(str(error));raise SystemExit(2)
