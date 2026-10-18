/* RAM-disk-only monochrome status display for the iPhone 4 framebuffer. */
typedef unsigned int u32;
typedef unsigned long usize;
extern int IOMobileFramebufferGetMainDisplay(void **);
extern int IOMobileFramebufferGetLayerDefaultSurface(void *, int, void **);
extern usize IOSurfaceGetWidth(void *);
extern usize IOSurfaceGetHeight(void *);
extern usize IOSurfaceGetBytesPerRow(void *);
extern u32 IOSurfaceGetPixelFormat(void *);
extern void *IOSurfaceGetBaseAddress(void *);
extern int IOSurfaceLock(void *, u32, u32 *);
extern int IOSurfaceUnlock(void *, u32, u32 *);
extern int open(const char *, int, ...);
extern int close(int);
extern long read(int, void *, usize);
extern long write(int, const void *, usize);
extern void *malloc(usize);
extern void free(void *);
extern int access(const char *, int);
extern int getuid(void);
extern int strcmp(const char *, const char *);
extern int snprintf(char *, usize, const char *, ...);
extern int usleep(unsigned int);

static int fail(const char *s, usize n) { write(2,s,n); return 1; }
#define FAIL(s) fail(s,sizeof(s)-1)
static int exact(int fd, void *p, usize n) {
    while (n) { long k=read(fd,p,n); if(k<=0)return 0; p=(char *)p+k; n-=k; }
    return 1;
}

int remed1st_main(int argc, char **argv) {
    int probe=argc==2 && !strcmp(argv[1],"--probe");
    if (getuid()!=0) return FAIL("Framebuffer access requires root.\n");
    if (!probe && (access("/dev/md0",0) || !access("/System/Library/CoreServices/SpringBoard.app/SpringBoard",0)))
        return FAIL("Drawing is allowed only in the SSH ramdisk.\n");
    void *display=0,*surface=0;
    int found=0;
    for (int i=0;i<40;i++) {
        if (!IOMobileFramebufferGetMainDisplay(&display) && display &&
            !IOMobileFramebufferGetLayerDefaultSurface(display,0,&surface) && surface) {found=1;break;}
        usleep(100000);
    }
    if(!found)return FAIL("The default framebuffer surface is unavailable.\n");
    usize width=IOSurfaceGetWidth(surface),height=IOSurfaceGetHeight(surface),stride=IOSurfaceGetBytesPerRow(surface);
    u32 format=IOSurfaceGetPixelFormat(surface);
    if(probe) {
        char s[128];int n=snprintf(s,sizeof(s),"Framebuffer: %lux%lu stride=%lu format=0x%x\n",width,height,stride,format);
        write(1,s,n);return 0;
    }
    if(width!=640 || height!=960 || stride<width*4 || stride>width*8)
        return FAIL("Unexpected framebuffer geometry. No pixels were written.\n");
    if(format!=0x42475241 && format!=0x41524742)
        return FAIL("Unsupported framebuffer pixel format. No pixels were written.\n");
    const char *file=argc==2?argv[1]:"/remed1st-screen/frame.rmd";
    if(argc>2)return FAIL("Usage: display [frame.rmd|--probe]\n");
    int fd=open(file,0);u32 header[4];
    if(fd<0)return FAIL("Status frame is missing.\n");
    if(!exact(fd,header,sizeof(header)) || header[0]!=0x31444d52 || header[1]!=640 || header[2]!=960 || header[3]!=1) {
        close(fd);return FAIL("Invalid status frame header.\n");
    }
    unsigned char *pixels=malloc(width*height);unsigned char extra;
    if(!pixels){close(fd);return FAIL("Could not allocate status pixels.\n");}
    if(!exact(fd,pixels,width*height) || read(fd,&extra,1)!=0) {
        close(fd);free(pixels);return FAIL("Status frame length mismatch.\n");
    }
    close(fd);
    if(IOSurfaceLock(surface,0,0)){free(pixels);return FAIL("Could not lock the framebuffer.\n");}
    unsigned char *base=IOSurfaceGetBaseAddress(surface);
    if(!base){IOSurfaceUnlock(surface,0,0);free(pixels);return FAIL("No framebuffer mapping.\n");}
    for(usize y=0;y<height;y++) {
        unsigned char *row=base+y*stride;
        for(usize x=0;x<width;x++) {
            unsigned char g=pixels[y*width+x];
            if(format==0x42475241){row[x*4]=g;row[x*4+1]=g;row[x*4+2]=g;row[x*4+3]=255;}
            else {row[x*4]=255;row[x*4+1]=g;row[x*4+2]=g;row[x*4+3]=g;}
        }
    }
    int result=IOSurfaceUnlock(surface,0,0);free(pixels);
    if(result)return FAIL("Could not finish the framebuffer update.\n");
    static const char ok[]="remed1st screen updated\n";write(1,ok,sizeof(ok)-1);return 0;
}
