/* Declare constants for the multiboot header. */
.set ALIGN,    1<<0             /* align loaded modules on page boundaries */
.set MEMINFO,  1<<1             /* provide memory map */
.set VIDEO,    1<<2             /* set video mode */
.set FLAGS,    ALIGN | MEMINFO | VIDEO
.set MAGIC,    0x1BADB002       /* 'magic number' lets bootloader find the header */
.set CHECKSUM, -(MAGIC + FLAGS) /* checksum of above, to prove we are multiboot */

/* Declare a multiboot header that marks the program as a kernel. */
.section .multiboot
.align 4
.long MAGIC
.long FLAGS
.long CHECKSUM
/* Padding for a.out kludge (not used, but required to reach video fields) */
.long 0, 0, 0, 0, 0
/* Video Mode fields */
.long 0    /* 0 = linear graphics mode */
.long 1024 /* width */
.long 768  /* height */
.long 32   /* depth (32 bits per pixel) */

/* Set up the stack. */
.section .bss
.align 16
stack_bottom:
.skip 16384 # 16 KiB
stack_top:

/* The linker script specifies _start as the entry point to the kernel */
.section .text
.global _start
.type _start, @function
_start:
	mov $stack_top, %esp

	/* Push EAX (magic number) and EBX (multiboot info structure) to kernel_main */
	push %eax
	push %ebx

	/* Transfer control to the main kernel. */
	call kernel_main

	/* Infinite loop if the kernel ever returns. */
	cli
1:	hlt
	jmp 1b
.size _start, . - _start
