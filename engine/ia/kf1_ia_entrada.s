# Entradas que llama el juego (ABI del EE: registros de 64 bits). Guardan s0-s8 y ra enteros y llaman a la
# función en C (o32), que solo guarda la mitad baja.
        .set noreorder
        .set mips3
        .text
        .globl KF1_Init_entrada
        .globl KF1_Think_entrada
KF1_Init_entrada:
        addiu $sp, $sp, -0x70
        sd $s0, 0x10($sp)
        sd $s1, 0x18($sp)
        sd $s2, 0x20($sp)
        sd $s3, 0x28($sp)
        sd $s4, 0x30($sp)
        sd $s5, 0x38($sp)
        sd $s6, 0x40($sp)
        sd $s7, 0x48($sp)
        sd $fp, 0x50($sp)
        sd $ra, 0x58($sp)
        jal KF1_Init
        nop
        b fin
        nop
KF1_Think_entrada:
        addiu $sp, $sp, -0x70
        sd $s0, 0x10($sp)
        sd $s1, 0x18($sp)
        sd $s2, 0x20($sp)
        sd $s3, 0x28($sp)
        sd $s4, 0x30($sp)
        sd $s5, 0x38($sp)
        sd $s6, 0x40($sp)
        sd $s7, 0x48($sp)
        sd $fp, 0x50($sp)
        sd $ra, 0x58($sp)
        jal KF1_Think
        nop
fin:
        ld $s0, 0x10($sp)
        ld $s1, 0x18($sp)
        ld $s2, 0x20($sp)
        ld $s3, 0x28($sp)
        ld $s4, 0x30($sp)
        ld $s5, 0x38($sp)
        ld $s6, 0x40($sp)
        ld $s7, 0x48($sp)
        ld $fp, 0x50($sp)
        ld $ra, 0x58($sp)
        jr $ra
        addiu $sp, $sp, 0x70
