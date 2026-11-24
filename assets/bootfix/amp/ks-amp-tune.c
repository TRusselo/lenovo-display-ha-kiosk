/* ks-amp-tune: lower the speaker amp's bass boost and flatten its compressor, after Lenovo's load.
 *
 * The amp is a TI TAS5825M on I2C bus 1, address 0x49. Lenovo's Things app (sparrow.oem) loads its tuning
 * once at boot; this waits for that, checks the tuning is one of Lenovo's, then rewrites:
 *   - the bass peak: +9 dB -> +3 dB at 79 Hz (book 0x8C, page 0x16, 0x1C-0x2F);
 *   - each compressor band's expander slope, compressor slope and their offset (k0, k1, off1) -> 0.
 *     The limiter (k2) stays: it protects the speaker.
 * lhk/amp.py holds the design and tests/test_amp.py checks the tables below against it. Lenovo's tuning
 * comes back with the next boot if this file is removed.
 *
 * Started by ks-boot-fix.rc. The file is labelled peripheralman_exec, so init starts it in the domain of
 * Android Things' peripheral daemon, the one allowed to open /dev/i2c-1.
 *
 * "ks-amp-tune check" only reads, and prints tuned, stock, not-loaded, unknown or error.
 * Exit status: 0 tuned now or already, 2 an unknown tuning (left alone), 3 Lenovo's load never came,
 * 4 an I2C error.
 *
 * Freestanding: no libc, so it runs on any of the displays' Android builds. Build:
 *   clang --target=armv7a-linux-gnueabi -mfloat-abi=soft -Os -ffreestanding -fno-stack-protector \
 *         -nostdlib -static -fuse-ld=lld -o ks-amp-tune ks-amp-tune.c
 */

static const unsigned char BASS[] = {         /* +3 dB peak, 78.8 Hz, Q 1.1: b0, b1/2, b2, -a1/2, -a2 */
    0x7f, 0xff, 0xff, 0xff, 0x80, 0xb7, 0x50, 0x99, 0x7e, 0x94, 0xd6, 0x60,
    0x7f, 0x7d, 0x81, 0x6d, 0x81, 0x01, 0x84, 0x25,
};
static const unsigned char STOCK_SIG[] = {    /* b1/2 of Lenovo's bass filters: the 8" today, an older app */
    0x81, 0x02, 0x32, 0x3f, 0x83, 0xa7, 0xa5, 0xd4,
};
static const unsigned char OURS_SIG[] = { 0x80, 0xb7, 0x50, 0x99 };
static const unsigned char FLAT[] = {         /* page, register of each word set to 0 */
    0x1a, 0x78, 0x1a, 0x7c, 0x1b, 0x14, 0x1b, 0x28, 0x1b, 0x2c,
    0x1b, 0x3c, 0x1b, 0x50, 0x1b, 0x54, 0x1b, 0x64,
};
static const unsigned char OFF2[] = {         /* each band's off2: 0 in every tuning we know */
    0x1b, 0x18, 0x1b, 0x40, 0x1b, 0x68,
};

static long sc(long n, long a, long b, long c) {
    register long r7 asm("r7") = n;
    register long r0 asm("r0") = a;
    register long r1 asm("r1") = b;
    register long r2 asm("r2") = c;
    asm volatile("svc 0" : "+r"(r0) : "r"(r7), "r"(r1), "r"(r2) : "memory");
    return r0;
}
static long sc4(long n, long a, long b, long c, long d) {
    register long r7 asm("r7") = n;
    register long r0 asm("r0") = a;
    register long r1 asm("r1") = b;
    register long r2 asm("r2") = c;
    register long r3 asm("r3") = d;
    asm volatile("svc 0" : "+r"(r0) : "r"(r7), "r"(r1), "r"(r2), "r"(r3) : "memory");
    return r0;
}
#define SYS_EXIT 1
#define SYS_READ 3
#define SYS_WRITE 4
#define SYS_OPEN 5
#define SYS_IOCTL 54
#define SYS_NANOSLEEP 162
#define SYS_RT_SIGACTION 174
#define I2C_SLAVE 0x0703
#define O_RDWR 2

/* Something at boot sent it SIGINT a second after init started it (8", 2026-11-23), so the stop signals
   are ignored: a half-done write would leave the amp on a DSP page. init still stops it with SIGKILL. */
static void ignore_stop_signals(void) {
    static const int sigs[] = {1, 2, 3, 13, 15};      /* HUP, INT, QUIT, PIPE, TERM */
    long act[5] = {1, 0, 0, 0, 0};                     /* handler SIG_IGN, flags, restorer, mask */
    for (unsigned i = 0; i < sizeof sigs / sizeof sigs[0]; i++)
        sc4(SYS_RT_SIGACTION, sigs[i], (long)act, 0, 8);
}

static long fd;
static void say(const char *s) { int n = 0; while (s[n]) n++; sc(SYS_WRITE, 1, (long)s, n); }
static void quit(int code) { sc(SYS_EXIT, code, 0, 0); for (;;) {} }
static void nap(long secs) { long ts[2] = {secs, 0}; sc(SYS_NANOSLEEP, (long)ts, 0, 0); }

static int put(unsigned char reg, unsigned char val) {
    unsigned char b[2] = {reg, val};
    return sc(SYS_WRITE, fd, (long)b, 2) == 2;
}
static int get(unsigned char reg, unsigned char *val) {
    return sc(SYS_WRITE, fd, (long)&reg, 1) == 1 && sc(SYS_READ, fd, (long)val, 1) == 1;
}
static int go(unsigned char book, unsigned char page) {
    return put(0x00, 0) && put(0x7f, book) && put(0x00, page);
}
static int same(const unsigned char *a, const unsigned char *b) {
    return a[0] == b[0] && a[1] == b[1] && a[2] == b[2] && a[3] == b[3];
}
static int read4(unsigned char page, unsigned char reg, unsigned char *out) {
    if (!go(0x8c, page)) return 0;
    for (int i = 0; i < 4; i++) if (!get(reg + i, out + i)) return 0;
    return 1;
}

/* 0 not loaded yet, 1 Lenovo's tuning, 2 ours, 3 unknown, -1 I2C error. Leaves book 0, page 0. */
static int state(void) {
    unsigned char sig[4];
    int ok = read4(0x16, 0x20, sig), s = 3;
    if (ok) {
        if (same(sig, OURS_SIG)) s = 2;
        else if (same(sig, STOCK_SIG) || same(sig, STOCK_SIG + 4)) s = 1;
        else if (!sig[0] && !sig[1] && !sig[2] && !sig[3]) s = 0;   /* the amp's own default: no filter */
    }
    if (!go(0x00, 0x00)) return -1;
    return ok ? s : -1;
}

static int idle(void) {
    unsigned char book, page;
    return get(0x7f, &book) && get(0x00, &page) && book == 0 && page == 0;
}

static int layout_known(void) {
    for (unsigned i = 0; i < sizeof OFF2; i += 2) {
        unsigned char w[4];
        if (!read4(OFF2[i], OFF2[i + 1], w) || w[0] || w[1] || w[2] || w[3]) return 0;
    }
    return 1;
}

static int tune(void) {
    if (!go(0x8c, 0x16)) return 0;
    for (int i = 0; i < 20; i++) if (!put(0x1c + i, BASS[i])) return 0;
    for (unsigned i = 0; i < sizeof FLAT; i += 2) {
        if (!go(0x8c, FLAT[i])) return 0;
        for (int j = 0; j < 4; j++) if (!put(FLAT[i + 1] + j, 0)) return 0;
    }
    /* The swap flag: the DSP takes the new coefficients. */
    return go(0x8c, 0x23) && put(0x14, 0) && put(0x15, 0) && put(0x16, 0) && put(0x17, 1);
}

void main_c(long *sp) {
    int argc = sp[0];
    char **argv = (char **)(sp + 1);
    int check = argc > 1 && argv[1][0] == 'c';
    ignore_stop_signals();
    char dev[] = "/dev/i2c-1";
    fd = sc(SYS_OPEN, (long)dev, O_RDWR, 0);
    if (fd < 0 || sc(SYS_IOCTL, fd, I2C_SLAVE, 0x49) < 0) { say("error\n"); quit(4); }

    if (check) {
        static const char *const words[] = {"not-loaded\n", "stock\n", "tuned\n", "unknown\n"};
        int s = idle() ? state() : -1;
        say(s < 0 ? "error\n" : words[s]);
        quit(0);
    }

    /* Lenovo writes its ~1,500 registers in one burst, switching book and page as it goes, and never
       again. Look only when the amp has sat on book 0, page 0 for a few seconds, so a look can't send
       one of Lenovo's writes to the wrong page. */
    int calm = 0;
    for (int t = 0; t < 600; t += 2) {
        nap(2);
        if (!idle()) { calm = 0; continue; }
        if (++calm < 3) continue;
        calm = 0;
        int s = state();
        if (s == 2) quit(0);
        if (s == 3) quit(2);
        if (s < 0) quit(4);
        if (s == 0) continue;
        nap(5);                                  /* Lenovo's last writes come just after the filters */
        if (!idle() || state() != 1) continue;
        if (!layout_known()) { go(0, 0); quit(2); }
        int ok = tune() && go(0, 0) && state() == 2;
        go(0, 0);
        quit(ok ? 0 : 4);
    }
    quit(3);
}

asm(".global _start\n_start:\n mov r0, sp\n bl main_c\n");
