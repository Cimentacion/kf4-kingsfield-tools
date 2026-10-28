/* IA propia para los bichos del King's Field (nivel 0): el Kraken y los pulpitos.
 *
 * Como en el King's Field (docs/kf1_ia.md): cada "fotograma de decisión" cada acción saca un número al azar
 * de 0 a su peso y gana la mayor. Acciones: girarse hacia ti (y andar, si el bicho anda) y los tres latigazos,
 * cada uno solo si estás a su alcance, delante y a su altura. El Kraken no anda; solo se gira (desde 12 m).
 *
 * Se monta sobre lo que ya tiene el juego (King's Field IV, SLES_509.20; nombres de kfiv-decomp):
 *   Beetle_Init        prepara al bicho (mover, golpe recibido, muerte...) y luego se cambia su "pensar"
 *   EntityAi_Move      el girarse/andar (con move_command), EntityAi_MeleeAttack el latigazo (con sus
 *                      ventanas de golpe del chr.prm), EntityAi_SensePlayer / StepState el verte.
 *
 * Datos del chr.prm que usa (registro de 0x450 bytes):
 *   0x240 + 0x88 i   latigazo i: +0 peso (0 = no), +4 alcance mínimo, +6 máximo (cm), +8 ángulo (rad),
 *                    +0x0E desvío (grados)
 *   0x436 / 0x438    distancias que mantiene si anda (cerca / lejos, cm); lejos = 0: no anda
 *   0x43A            distancia a la que empieza a hacerte caso (cm)
 *   0x43C            distancia a la que deja de hacerte caso si ya te seguía (cm)
 *   0x43E            fotogramas entre decisiones mientras se gira
 *   0x14             peso de girarse (byte 0: si es nuevo; byte 1: si ya se estaba girando)
 *
 * Se compila para MIPS (o32, solo float) y se llama desde las entradas de kf1_ia_entrada.s, que guardan los
 * registros enteros de 64 bits del EE.
 */

typedef unsigned char u8;
typedef signed char s8;
typedef unsigned short u16;
typedef short s16;
typedef unsigned int u32;
typedef int s32;
typedef float f32;

/* direcciones del juego (las pone el enlazador: kf1_ia.py) */
extern void Beetle_Init(void *e);
extern void EntityAi_SensePlayer(void *e, s32 mode);
extern void EntityAi_StepState(void *e);
extern s32 EntityAi_StartAction(void *e, void (*handler)(void *), s32 run_now);
extern s32 EntityAi_TurnCommand(void *e);
extern void EntityAi_MeleeAttack(void *e);
extern s32 rand(void);
extern u32 frame_counter;
extern u8 player_state[];

void KF1_Think(void *e, s32 run_now);
extern void KF1_Think_entrada(void *e, s32 run_now);    /* kf1_ia_entrada.s */

#define B(e, o)  (*(volatile u8 *)((u8 *)(e) + (o)))
#define SB(e, o) (*(volatile s8 *)((u8 *)(e) + (o)))
#define H(e, o)  (*(volatile u16 *)((u8 *)(e) + (o)))
#define SH(e, o) (*(volatile s16 *)((u8 *)(e) + (o)))
#define W(e, o)  (*(volatile u32 *)((u8 *)(e) + (o)))
#define F(e, o)  (*(volatile f32 *)((u8 *)(e) + (o)))
#define P(e, o)  (*(void *volatile *)((u8 *)(e) + (o)))

/* Entity */
#define E_MODEL        0x00
#define E_PARAMS       0x0C
#define E_RADIUS       0x38
#define E_HEIGHT       0x3C
#define E_HANDLER      0x54
#define E_TARGET       0x5C
#define E_DIST         0x64
#define E_HEADING      0x68
#define E_ACT_TIMER    0xA0
#define E_ATK_DELAY    0xA2
#define E_BUSY         0xC6
#define E_MOVE_CMD     0xC8
#define E_STATE        0xCC
#define E_SPAWN_INDEX  0xD7
#define E_FLAGS_LO     0xD8
#define E_FLAGS_HI     0xDC
#define E_THINK        0xE0
#define E_ANIMATE      0xE4
#define E_MOVE         0xF8
/* bytes propios: Entity+0x170.. (relleno que Beetle_Init pone a cero) */
#define E_GIRANDO      0x17C
/* EntityModel */
#define M_POS_Y        0xC4
#define M_ROT_Y        0xD4
#define M_SCALE_X      0xE0
/* EntityParams */
#define P_PESO_GIRO    0x14
#define P_LATIGO       0x240
#define P_CERCA        0x436
#define P_LEJOS        0x438
#define P_EMPIEZA      0x43A
#define P_SIGUE        0x43C
#define P_DECIDE       0x43E

#define PI_F      3.1415927f
#define DOS_PI    6.2831855f

#define ESTADO_LO_VE     2
#define MOVE_FORWARD     0x1
#define MOTION_STEP_MASK (7u << 11)       /* flags bits 11-13 */
#define MOTION_STEP_MOVE (1u << 11)
#define ATAQUE_MASK      (7u << 25)       /* flags bits 57 (a distancia) y 58-59 (cuál) */

/* a entre -pi y pi (sin bucles: el R5900 falla en bucles muy cortos; aquí basta con dos vueltas) */
static f32 envolver(f32 a) {
    if (a > PI_F) {
        a -= DOS_PI;
    }
    if (a > PI_F) {
        a -= DOS_PI;
    }
    if (a < -PI_F) {
        a += DOS_PI;
    }
    if (a < -PI_F) {
        a += DOS_PI;
    }
    return a;
}

static f32 absf(f32 a) {
    return a < 0.0f ? -a : a;
}

static s32 azar(s32 hasta) {      /* 0..hasta */
    if (hasta <= 0) {
        return 0;
    }
    return rand() % (hasta + 1);
}

/* ¿estás al alcance del latigazo i? */
static s32 al_alcance(void *e, u8 *prm, s32 i) {
    u8 *l = prm + P_LATIGO + 0x88 * i;
    void *m = P(e, E_MODEL);
    f32 desvio, dif, d, lejos, cerca, y, py;

    if (B(l, 0) == 0) {
        return 0;
    }
    desvio = (f32)SH(l, 0x0E) * (PI_F / 180.0f);
    if (F(m, M_SCALE_X) < 0.0f) {
        desvio = -desvio;
    }
    dif = absf(envolver(F(e, E_HEADING) - envolver(F(m, M_ROT_Y) + desvio)));
    if (!(dif < F(l, 8))) {
        return 0;
    }
    d = F(e, E_DIST);
    lejos = (f32)H(l, 6) + F(e, E_RADIUS) + 100.0f;
    cerca = H(l, 4) ? (f32)H(l, 4) + F(e, E_RADIUS) + 100.0f : 0.0f;
    if (!(d < lejos) || d < cerca) {
        return 0;
    }
    /* a su altura (como EntityAi_PickAttack; y crece hacia abajo) */
    y = F(m, M_POS_Y);
    py = F(player_state, 4);
    if (y < py - 230.0f || y > py + F(e, E_HEIGHT)) {
        return 0;
    }
    return 1;
}

static void quieto(void *e, s32 run_now) {
    W(e, E_FLAGS_LO) &= ~MOTION_STEP_MASK;
    H(e, E_MOVE_CMD) = 0;
    B(e, E_GIRANDO) = 0;
    EntityAi_StartAction(e, (void (*)(void *))P(e, E_MOVE), run_now);
}

void KF1_Think(void *e, s32 run_now) {
    u8 *prm = (u8 *)P(e, E_PARAMS);
    s32 mejor, i, s, cual, mando, anda;
    f32 d;

    if (frame_counter % 10u == (u32)B(e, E_SPAWN_INDEX) % 10u) {
        EntityAi_SensePlayer(e, 2);      /* 2: aunque algo tape la vista, te sigue viendo */
    }
    if (H(e, E_BUSY) != 0) {
        return;
    }
    EntityAi_StepState(e);
    P(e, E_TARGET) = player_state;
    d = F(e, E_DIST);
    if (SB(e, E_STATE) != ESTADO_LO_VE) {
        quieto(e, run_now);
        return;
    }
    if (B(e, E_GIRANDO) ? d > (f32)H(prm, P_SIGUE) : d > (f32)H(prm, P_EMPIEZA)) {
        quieto(e, run_now);
        return;
    }
    /* mientras se gira (o anda) no decide en cada fotograma, como su "moverse" del King's Field */
    cual = -1;
    mejor = -1;
    if (!(B(e, E_GIRANDO) && H(e, E_ACT_TIMER) != 0) && B(e, E_ATK_DELAY) == 0) {
        mejor = azar(B(prm, P_PESO_GIRO + (B(e, E_GIRANDO) ? 1 : 0)));
        for (i = 0; i < 3; i++) {
            if (al_alcance(e, prm, i)) {
                s = azar(B(prm, P_LATIGO + 0x88 * i));
                if (s > mejor) {
                    mejor = s;
                    cual = i;
                }
            }
        }
    }
    if (cual >= 0) {
        W(e, E_FLAGS_HI) = (W(e, E_FLAGS_HI) & ~ATAQUE_MASK) | ((u32)cual << 26);
        B(e, E_GIRANDO) = 0;
        EntityAi_StartAction(e, EntityAi_MeleeAttack, run_now);
        return;
    }
    if (mejor >= 0) {           /* nueva decisión: girarse (y andar) un rato */
        H(e, E_ACT_TIMER) = H(prm, P_DECIDE);
    }
    /* girarse hacia ti; si anda, acercarse hasta su distancia lejana (el pulpito: 2,6 m) */
    mando = EntityAi_TurnCommand(e);
    anda = SH(prm, P_LEJOS) > 0 && d > (f32)SH(prm, P_LEJOS);
    W(e, E_FLAGS_LO) &= ~MOTION_STEP_MASK;
    if (anda) {
        mando |= MOVE_FORWARD;
        W(e, E_FLAGS_LO) |= MOTION_STEP_MOVE;     /* el arrastrarse lleva el avance en la animación */
    }
    H(e, E_MOVE_CMD) = (u16)mando;
    B(e, E_GIRANDO) = 1;
    EntityAi_StartAction(e, (void (*)(void *))P(e, E_MOVE), run_now);
}

void KF1_Init(void *e) {
    Beetle_Init(e);
    P(e, E_THINK) = (void *)KF1_Think_entrada;
    B(e, E_GIRANDO) = 0;
}
