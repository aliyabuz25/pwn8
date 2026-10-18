/* Standalone iOS 5 system notice; no SpringBoard code injection. */
typedef const void *CFStringRef;
typedef unsigned long CFOptionFlags;
typedef unsigned int CFStringEncoding;
extern CFStringRef CFStringCreateWithCString(const void *, const char *, CFStringEncoding);
extern int CFUserNotificationDisplayNotice(double, CFOptionFlags, const void *, const void *,
                                           const void *, CFStringRef, CFStringRef, CFStringRef);
extern void CFRelease(const void *);
extern void exit(int) __attribute__((noreturn));
extern long write(int, const void *, unsigned long);

void remed1st_start(void) {
    CFStringRef title = CFStringCreateWithCString(0, "remed1st-beta", 0x08000100);
    CFStringRef message = CFStringCreateWithCString(0,
        "Thanks for using remed1st-beta @aliyabuz25", 0x08000100);
    CFStringRef button = CFStringCreateWithCString(0, "OK", 0x08000100);
    if (!title || !message || !button) exit(2);
    int result = CFUserNotificationDisplayNotice(20.0, 3, 0, 0, 0, title, message, button);
    CFRelease(button); CFRelease(message); CFRelease(title);
    if (result) exit(3);
    static const char accepted[] = "remed1st notification submitted\n";
    write(1, accepted, sizeof(accepted)-1);
    exit(0);
}
