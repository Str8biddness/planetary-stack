all: synthesus.iso

boot.o: boot.s
	as --32 boot.s -o boot.o

kernel.o: kernel.cpp
	g++ -m32 -c kernel.cpp -o kernel.o -std=gnu++11 -ffreestanding -O2 -Wall -Wextra -fno-exceptions -fno-rtti

synthesus.bin: boot.o kernel.o linker.ld
	g++ -m32 -T linker.ld -o synthesus.bin -ffreestanding -O2 -nostdlib boot.o kernel.o

synthesus.iso: synthesus.bin grub.cfg
	mkdir -p isodir/boot/grub
	cp synthesus.bin isodir/boot/synthesus.bin
	cp grub.cfg isodir/boot/grub/grub.cfg
	grub-mkrescue -o synthesus.iso isodir

clean:
	rm -f boot.o kernel.o synthesus.bin synthesus.iso
	rm -rf isodir
