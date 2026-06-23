#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "font8x8_basic.h"

// I/O Port operations for hardware interaction
static inline void outb(uint16_t port, uint8_t val) {
    asm volatile ( "outb %0, %1" : : "a"(val), "Nd"(port) );
}

static inline uint8_t inb(uint16_t port) {
    uint8_t ret;
    asm volatile ( "inb %1, %0" : "=a"(ret) : "Nd"(port) );
    return ret;
}

struct multiboot_info {
    uint32_t flags;
    uint32_t mem_lower;
    uint32_t mem_upper;
    uint32_t boot_device;
    uint32_t cmdline;
    uint32_t mods_count;
    uint32_t mods_addr;
    uint32_t num;
    uint32_t size;
    uint32_t addr;
    uint32_t shndx;
    uint32_t mmap_length;
    uint32_t mmap_addr;
    uint32_t drives_length;
    uint32_t drives_addr;
    uint32_t config_table;
    uint32_t boot_loader_name;
    uint32_t apm_table;
    
    uint32_t vbe_control_info;
    uint32_t vbe_mode_info;
    uint16_t vbe_mode;
    uint16_t vbe_interface_seg;
    uint16_t vbe_interface_off;
    uint16_t vbe_interface_len;

    uint64_t framebuffer_addr;
    uint32_t framebuffer_pitch;
    uint32_t framebuffer_width;
    uint32_t framebuffer_height;
    uint8_t framebuffer_bpp;
    uint8_t framebuffer_type;
    uint8_t color_info[6];
} __attribute__((packed));

uint32_t* lfb;
uint32_t screen_width;
uint32_t screen_height;
uint32_t screen_pitch;

void put_pixel(uint32_t x, uint32_t y, uint32_t color) {
    if (x >= screen_width || y >= screen_height) return;
    uint32_t offset = (y * (screen_pitch / 4)) + x;
    lfb[offset] = color;
}

void draw_rect(uint32_t start_x, uint32_t start_y, uint32_t width, uint32_t height, uint32_t color) {
    for (uint32_t y = start_y; y < start_y + height; y++) {
        for (uint32_t x = start_x; x < start_x + width; x++) {
            put_pixel(x, y, color);
        }
    }
}

// Draw a single character using the 8x8 font
void draw_char(char c, uint32_t x, uint32_t y, uint32_t color) {
    unsigned char* bitmap = font8x8_basic[(uint8_t)c];
    for (int row = 0; row < 8; row++) {
        for (int col = 0; col < 8; col++) {
            if (bitmap[row] & (1 << col)) {
                put_pixel(x + col, y + row, color);
            }
        }
    }
}

// Draw a string using the 8x8 font (scaled 2x for visibility)
void draw_string_2x(const char* str, uint32_t x, uint32_t y, uint32_t color) {
    int i = 0;
    while (str[i]) {
        unsigned char* bitmap = font8x8_basic[(uint8_t)str[i]];
        for (int row = 0; row < 8; row++) {
            for (int col = 0; col < 8; col++) {
                if (bitmap[row] & (1 << col)) {
                    uint32_t px = x + (i * 16) + (col * 2);
                    uint32_t py = y + (row * 2);
                    put_pixel(px, py, color);
                    put_pixel(px+1, py, color);
                    put_pixel(px, py+1, color);
                    put_pixel(px+1, py+1, color);
                }
            }
        }
        i++;
    }
}

void clear_screen(uint32_t color) {
    draw_rect(0, 0, screen_width, screen_height, color);
}

// --- PS/2 Mouse Driver ---
void mouse_wait(uint8_t a_type) {
    uint32_t _time_out = 100000;
    if (a_type == 0) {
        while (_time_out--) {
            if ((inb(0x64) & 1) == 1) return;
        }
    } else {
        while (_time_out--) {
            if ((inb(0x64) & 2) == 0) return;
        }
    }
}

void mouse_write(uint8_t a_write) {
    mouse_wait(1); outb(0x64, 0xD4);
    mouse_wait(1); outb(0x60, a_write);
}

uint8_t mouse_read() {
    mouse_wait(0); return inb(0x60);
}

void mouse_install() {
    uint8_t _status;
    mouse_wait(1); outb(0x64, 0xA8);
    mouse_wait(1); outb(0x64, 0x20);
    mouse_wait(0); _status = (inb(0x60) | 2);
    mouse_wait(1); outb(0x64, 0x60);
    mouse_wait(1); outb(0x60, _status);
    mouse_write(0xF6); mouse_read();
    mouse_write(0xF4); mouse_read();
}

int32_t mouse_x = 512;
int32_t mouse_y = 384;
uint32_t cursor_bg[6][6];

void save_cursor_bg(int32_t x, int32_t y) {
    for(int i=0; i<6; i++) {
        for(int j=0; j<6; j++) {
            if (x+j < (int32_t)screen_width && y+i < (int32_t)screen_height) {
                cursor_bg[i][j] = lfb[((y+i) * (screen_pitch/4)) + (x+j)];
            }
        }
    }
}

void restore_cursor_bg(int32_t x, int32_t y) {
    for(int i=0; i<6; i++) {
        for(int j=0; j<6; j++) {
            if (x+j < (int32_t)screen_width && y+i < (int32_t)screen_height) {
                put_pixel(x+j, y+i, cursor_bg[i][j]);
            }
        }
    }
}

void draw_cursor(int32_t x, int32_t y) {
    draw_rect(x, y, 6, 6, 0xFFFFFF);
    draw_rect(x+1, y+1, 4, 4, 0x000000); // Black center
}

extern "C" void kernel_main(multiboot_info* mbd, uint32_t magic) {
    if (magic != 0x2BADB002 || !(mbd->flags & (1 << 12))) return;

    lfb = (uint32_t*)(uint32_t)mbd->framebuffer_addr;
    screen_width = mbd->framebuffer_width;
    screen_height = mbd->framebuffer_height;
    screen_pitch = mbd->framebuffer_pitch;

    // Background
    clear_screen(0x0f172a); 

    // Glass Panel
    draw_rect(screen_width / 4, screen_height / 4, screen_width / 2, screen_height / 2, 0x1e293b); 
    draw_rect(screen_width / 4, screen_height / 4, screen_width / 2, 5, 0x38bdf8); 

    // Draw Bitmap Fonts!
    draw_string_2x("SYNTHESUS KERNEL ONLINE", (screen_width / 4) + 20, (screen_height / 4) + 30, 0xe2e8f0);
    draw_string_2x("PS/2 Peripheral Polling: Active", (screen_width / 4) + 20, (screen_height / 4) + 70, 0x94a3b8);
    draw_string_2x("AIVM Subsystem: Mounted", (screen_width / 4) + 20, (screen_height / 4) + 110, 0x94a3b8);

    // Green indicator
    draw_rect((screen_width / 4) + 20, (screen_height / 4) + 160, 10, 10, 0x4ade80);
    draw_string_2x("AIVM Bridge", (screen_width / 4) + 40, (screen_height / 4) + 158, 0x4ade80);

    mouse_install();
    
    int mouse_cycle = 0;
    uint8_t mouse_byte[3];

    save_cursor_bg(mouse_x, mouse_y);
    draw_cursor(mouse_x, mouse_y);

    while (true) {
        if (inb(0x64) & 1) { 
            uint8_t status = inb(0x64);
            if (status & 0x20) { 
                mouse_byte[mouse_cycle++] = inb(0x60);
                if (mouse_cycle == 3) {
                    mouse_cycle = 0;
                    restore_cursor_bg(mouse_x, mouse_y);

                    // Decode PS/2 packet
                    int x_rel = mouse_byte[1] - ((mouse_byte[0] << 4) & 0x100);
                    int y_rel = mouse_byte[2] - ((mouse_byte[0] << 3) & 0x100);

                    mouse_x += x_rel;
                    mouse_y -= y_rel; // Y is inverted in screen space

                    if (mouse_x < 0) mouse_x = 0;
                    if (mouse_y < 0) mouse_y = 0;
                    if (mouse_x >= (int32_t)screen_width - 6) mouse_x = screen_width - 6;
                    if (mouse_y >= (int32_t)screen_height - 6) mouse_y = screen_height - 6;

                    save_cursor_bg(mouse_x, mouse_y);
                    draw_cursor(mouse_x, mouse_y);
                }
            } else {
                inb(0x60); // Flush keyboard
            }
        }
    }
}
