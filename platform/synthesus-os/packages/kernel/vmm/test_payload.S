.code16
.global _start

_start:
    # 1. Serial Hello
    mov $0x3F8, %dx
    mov $'A', %al
    outb %al, %dx
    mov $'I', %al
    outb %al, %dx
    mov $'O', %al
    outb %al, %dx
    mov $'S', %al
    outb %al, %dx
    mov $'\n', %al
    outb %al, %dx

    # 2. VQD MMIO Trigger (Pauli-X)
    # Write 2 to 0xF1000020
    mov $0xF1000020, %ebx
    mov $2, %eax
    mov %eax, (%ebx)

    # 3. VQD Compute (COMMAND=1)
    # Write 1 to 0xF1000048
    mov $0xF1000048, %ebx
    mov $1, %eax
    mov %eax, (%ebx)

    hlt
