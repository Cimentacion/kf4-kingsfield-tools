# King's Field (JP2 / US KF1) - comportamiento de los monstruos (ingeniería inversa)

Objetivo: sacar del ejecutable del King's Field (GAME.EXE, PS-X EXE, carga en 0x80011000, 0x65800 bytes)
lo que hace cada monstruo, para copiarlo en IA propias del King's Field IV.

## Datos del nivel (FDAT.T, entrada 3*nivel+1)

Cuatro secciones (u32 tamaño + datos): clases, entidades (16 B), objetos (24 B), otra (2 KB).

### Clases (120 B cada una, 40 clases; luego, desde 40*120 = 0x12C0, el área de acciones)

| offset | qué |
|---|---|
| +0x00 | modelo (MO.T) |
| +0x12, +0x14 | se copian a la entidad +0x1C, +0x1E |
| +0x1A | vida (u16) |
| +0x1E | experiencia (u16) |
| +0x32 | escala (u16, 4096 = 1): a la entidad +0x48/+0x4A/+0x4C |
| +0x34 | flags (u32): a la entidad +0x28 (bit 0x80: ...) |
| +0x38..+0x74 | 16 punteros a acciones (offset desde 0x12C0; -1 = ninguna). Al cargar (0x80042244) se convierten en direcciones |

En memoria: tabla de clases en 0x801746E8 (40 x 0x78). Inicio de entidad desde su clase: 0x8003B848.
Para los NPC (modelo de NPC), el puntero +0x38 apunta a su diálogo (empieza por 0x70; códigos 0xF0/F1/FE).

### Acciones (longitud variable)

byte 0 = tipo de acción, byte 1 = número de animación (del MO.T del modelo), luego parámetros.
Tipos vistos: 0x00, 0x02 (golpe recibido), 0x03 (muerte), 0x04 (ataque de cerca), 0x05 (moverse), 0x13, 0x17,
0x18 (ataques del esqueleto), 0x19.

Kraken grande (clase 0, modelo 29, 1500 de vida, 450 de experiencia):
```
05 00 64 8c ff 00 00 00 80 00 00 00 00 00 20 00 10 27 e0 2e 00 00 00 00 14 00   moverse (anim 0)
04 01 a0 a0 51 00 00 00 96 00 00 00 ff 08 5a 1f 25 00 00 00 64 00 00 00 d0 07 a8 16   cerca (anim 1)
04 02 a0 a0 51 00 00 00 96 00 00 00 ff 08 5a 1f 25 00 00 00 78 00 00 00 d0 07 a8 16   cerca (anim 2)
04 03 78 78 51 00 00 00 96 00 00 00 ff 08 79 1f 1f 40 00 00 8c 00 00 00 d0 07 78 1e   cerca (anim 3)
02 04 ff 00 50 00 00 00 00 01 00 00 00 00                                         golpe recibido (anim 4)
03 05 00 00 4f 00 00 00 64 00 00 00 ff 00 01 00 20 40 25 00 00 00 80 00 be 40 20 00 10 00 20 00   muerte
```
La capucha (clase 17, modelo 30, 100 de vida) es OTRO monstruo en la misma casilla, con su propia acción 0x00.

## Ejecutable

- Entidades: 0x8016E608, 0x7C bytes cada una, 199 (0xC7). +1 modelo, +2 clase, +9 estado, +0x1A vida.
- Dos `switch` por modelo (ent+1, 123 casos): 0x80042EE0 (tabla 0x80012598) y 0x80045070 (tabla 0x80012788).
  Kraken (29): 0x80043F60 / 0x80045078; capucha (30): 0x80043F58 / 0x80045080.
- 0x80029C80..: uso de magias/objetos del jugador (no de monstruos).

Pendiente: encontrar dónde se interpreta el byte 0 de cada acción (qué hace cada tipo y qué significan sus
parámetros) y la parte propia de cada modelo en los dos switch.
