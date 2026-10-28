#!/usr/bin/env python3
"""Compila la IA propia de los bichos del King's Field (kf1_ia.c) para el ejecutable PAL del King's Field IV
(SLES_509.20) y deja kf1_ia.bin (código ya enlazado en IA_VA) y kf1_ia.json (entradas).

Hace falta clang y ld.lld (LLVM). El resultado va en el repositorio: el parche (kf4_valle.parche_kf1_ia) solo
lo copia en el ejecutable, así que quien juega no necesita compilar nada.

El EE (R5900) no es un MIPS cualquiera: se compila para MIPS II con flotantes simples (o32) y se comprueba que
solo haya instrucciones que el EE tiene. Sus comparaciones de flotantes son solo C.F, C.EQ, C.LT y C.LE; las
"desordenadas" (c.ult, c.ule...) que saca clang son iguales sin NaN y se cambian por las ordenadas.
"""
import json
import os
import struct
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
IA_VA = 0x01E5F200          # justo tras el final del ejecutable (_end = 0x1E5F1B0), antes del montón
# funciones y datos del juego (SLES_509.20; kfiv-decomp, US - 0x17C8 en el código del juego, - 0x840 en datos)
JUEGO = {
    "EntityAi_Guard": 0x180498,
    "EntityAi_SensePlayer": 0x1950A8,
    "EntityAi_StepState": 0x18D1F8,
    "EntityAi_StartAction": 0x1940F0,
    "EntityAi_TurnCommand": 0x18F418,
    "EntityAi_MeleeAttack": 0x180680,
    "rand": 0x2421A0,
    "frame_counter": 0x44DC54,
    "player_state": 0x413740,
    "player_weapon_step": 0x413998,
    "held_item_model_ptr": 0x44D6F8,
    "entity_type_handlers": 0x3E6600,
}
DATOS = ("frame_counter", "player_state", "player_weapon_step", "held_item_model_ptr", "entity_type_handlers")
CF = ["--target=mipsel-none-elf", "-march=mips2", "-msingle-float", "-mno-abicalls", "-fno-pic", "-G0", "-O2",
      "-ffreestanding", "-fno-builtin", "-fno-jump-tables", "-mno-check-zero-division", "-fomit-frame-pointer",
      "-ffinite-math-only", "-fno-signed-zeros", "-mstack-alignment=16", "-fno-unroll-loops"]

# opcodes principales que se permiten (MIPS II sin lo que el EE no tiene)
PERMITIDOS = {0x00, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F,
              0x11, 0x14, 0x15, 0x16, 0x17, 0x20, 0x21, 0x23, 0x24, 0x25, 0x28, 0x29, 0x2B, 0x31, 0x39,
              0x37, 0x3F, 0x01}
SPECIAL = {0x00, 0x02, 0x03, 0x04, 0x06, 0x07, 0x08, 0x09, 0x10, 0x11, 0x12, 0x13, 0x18, 0x19, 0x1A, 0x1B,
           0x21, 0x23, 0x24, 0x25, 0x26, 0x27, 0x2A, 0x2B, 0x0D}
COP1_S = {0x00, 0x01, 0x02, 0x03, 0x05, 0x06, 0x07, 0x24, 0x30, 0x32, 0x34, 0x36}


def revisar(code):
    out = bytearray(code)
    for i in range(0, len(out), 4):
        w = struct.unpack_from("<I", out, i)[0]
        op = w >> 26
        if op not in PERMITIDOS:
            raise SystemExit(f"instrucción no permitida en +{i:#x}: {w:08x}")
        if op == 0 and (w & 0x3F) not in SPECIAL:
            raise SystemExit(f"SPECIAL no permitida en +{i:#x}: {w:08x}")
        if op == 0x11:
            fmt = (w >> 21) & 0x1F
            if fmt == 0x10:                                   # .s
                fn = w & 0x3F
                if fn in (0x35, 0x37):                        # c.ult / c.ule -> c.lt / c.le (sin NaN)
                    w &= ~1
                    fn &= ~1
                    struct.pack_into("<I", out, i, w)
                if fn not in COP1_S:
                    raise SystemExit(f"flotante no permitida en +{i:#x}: {w:08x}")
            elif fmt == 0x14:                                 # .w: solo cvt.s.w
                if (w & 0x3F) != 0x20:
                    raise SystemExit(f"flotante .w no permitida en +{i:#x}: {w:08x}")
            elif fmt not in (0x00, 0x04, 0x08, 0x02, 0x06):   # mfc1 mtc1 bc1 cfc1 ctc1
                raise SystemExit(f"COP1 no permitida en +{i:#x}: {w:08x}")
    return bytes(out)


def main():
    tmp = os.path.join(AQUI, "build")
    os.makedirs(tmp, exist_ok=True)
    o1, o2 = os.path.join(tmp, "kf1_ia.o"), os.path.join(tmp, "entrada.o")
    subprocess.check_call(["clang", *CF, "-c", os.path.join(AQUI, "kf1_ia.c"), "-o", o1])
    subprocess.check_call(["clang", "--target=mipsel-none-elf", "-mno-abicalls", "-c", os.path.join(AQUI, "kf1_ia_entrada.s"),
                           "-o", o2])
    ld = os.path.join(tmp, "kf1_ia.ld")
    with open(ld, "w") as f:
        for k, v in JUEGO.items():
            f.write(f"{k} = {v:#x};\n")
        f.write(f"SECTIONS {{ . = {IA_VA:#x}; .text : {{ *(.text*) _fin_codigo = .; *(.rodata*) *(.data*) *(.sdata*) *(.bss*) "
                f"*(.sbss*) *(COMMON) }} /DISCARD/ : {{ *(.MIPS.abiflags) *(.reginfo) *(.comment) *(.pdr) }} }}\n")
    elf = os.path.join(tmp, "kf1_ia.elf")
    subprocess.check_call(["ld.lld", "-m", "elf32ltsmip", "-T", ld, "--no-check-sections", "-e", "KF1_Init_entrada", "-o", elf, o1, o2])
    binf = os.path.join(tmp, "kf1_ia.raw")
    subprocess.check_call(["llvm-objcopy", "-O", "binary", "-j", ".text", elf, binf])
    nm = subprocess.check_output(["llvm-nm", elf], text=True)
    sim = {l.split()[2]: int(l.split()[0], 16) for l in nm.splitlines() if len(l.split()) == 3}
    code = open(binf, "rb").read()
    n = sim['_fin_codigo'] - IA_VA
    code = revisar(code[:n]) + code[n:]
    marcos = subprocess.check_output(["llvm-objdump", "-d", "--no-show-raw-insn", elf], text=True)
    for l in marcos.splitlines():
        if "addiu\t$sp, $sp, -" in l:
            n = int(l.split("-")[-1].split()[0], 16)
            if n % 16:
                raise SystemExit("marco de pila sin alinear a 16: " + l)
    open(os.path.join(AQUI, "kf1_ia.bin"), "wb").write(code)
    info = {"va": IA_VA, "tam": len(code), "init": sim["KF1_Init_entrada"], "think": sim["KF1_Think_entrada"],
            "juego": JUEGO}
    # firmas: los 16 primeros bytes de cada función del juego que se llama (el parche no se pone si no cuadran)
    exe = sys.argv[1] if len(sys.argv) > 1 else None
    viejo = os.path.join(AQUI, "kf1_ia.json")
    if exe:
        e = open(exe, "rb").read()
        info["firmas"] = {k: e[v - 0xFF000:v - 0xFF000 + 16].hex() for k, v in JUEGO.items()
                          if k not in DATOS}
    elif os.path.isfile(viejo):
        info["firmas"] = json.load(open(viejo)).get("firmas", {})
    json.dump(info, open(os.path.join(AQUI, "kf1_ia.json"), "w"), indent=1)
    print(f"kf1_ia.bin: {len(code)} bytes en {IA_VA:#x}; init {info['init']:#x}, think {info['think']:#x}")


if __name__ == "__main__":
    sys.exit(main())
