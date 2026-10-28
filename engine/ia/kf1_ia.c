/* IA propia para los bichos del King's Field (JP2 = KF1 de EE.UU.) en el King's Field IV.
 *
 * Como en el King's Field (docs/kf1_ia.md, sacado de su GAME.EXE): en cada decisión cada acción posible saca un
 * número al azar de 0 a su peso y gana el mayor. Acciones (tipos del King's Field entre paréntesis):
 *   quieto (0x00)            siempre; peso nuevo / si ya estaba quieto
 *   pasear (0x01)            siempre; anda hacia un punto al azar cerca de donde apareció
 *   moverse (0x05)           si estás a menos de su distancia (más si ya te seguía): se gira hacia ti y, si
 *                            anda, va hacia ti. Justo después de un golpe, o si estás más cerca que su distancia
 *                            de apartarse, se aleja (si tiene andar hacia atrás; si no, se queda de cara a ti)
 *                            hasta que estás más lejos que la de dejar de apartarse. Su
 *                            peso se dobla justo después de un golpe (como allí)
 *   guardia (0x13)           si estás cerca, delante y atacando: EntityAi_Guard (animación 13)
 *   golpes 0-2 (0x04, 0x17, 0x18)  si estás a su alcance, delante y a su altura; su peso baja a 5/6 si estás más
 *                            lejos que donde llega el golpe y a 2/3 si estás pasada la mitad hasta su alcance
 *
 * Se monta sobre lo que ya tiene el juego (King's Field IV, SLES_509.20; nombres de kfiv-decomp): la preparación
 * del bicho del IV del que salen los huesos (su fila de entity_type_handlers: golpes recibidos, muerte, andar,
 * animar), y luego se cambia su "pensar" por KF1_Think. Los golpes son EntityAi_MeleeAttack (las ventanas de golpe
 * del chr.prm); andar y girarse, su "mover" con move_command.
 *
 * Datos (registro de 0x450 bytes del chr.prm):
 *   0x240 + 0x88 i   golpe i: +0 peso (0 = no), +4 alcance mínimo, +6 máximo (cm, más radio + 100), +8 ángulo
 *                    (rad), +0x0E desvío (grados), +0x30 radio extra del golpe
 *   BLOQUE (0x3F8, en el ataque a distancia 1, que no se usa):
 *     +0 tipo del IV cuya preparación se usa (5: el escarabajo)
 *     +2/+3 peso quieto (nuevo / seguir)   +4/+5 pasear   +6 moverse   +8/+9 guardia
 *     +0x0A u16 guardia: distancia (cm)    +0x0C u16 moverse: empieza (cm)   +0x0E sigue hasta (cm)
 *     +0x10 u16 se aparta si estás más cerca de (cm)   +0x12 u16 hasta que estás más lejos de (cm)
 *     +0x14 fotogramas por decisión al moverse (quieto y pasear: el triple)   +0x15 1: anda (0: solo se gira)
 *
 * Se compila para MIPS (o32, solo float) y se llama desde kf1_ia_entrada.s, que guarda los registros de 64 bits.
 */

typedef unsigned char u8;
typedef signed char s8;
typedef unsigned short u16;
typedef short s16;
typedef unsigned int u32;
typedef int s32;
typedef float f32;

/* direcciones del juego (las pone el enlazador: construir.py) */
extern void EntityAi_SensePlayer(void *e, s32 mode);
extern void EntityAi_StepState(void *e);
extern s32 EntityAi_StartAction(void *e, void (*handler)(void *), s32 run_now);
extern s32 EntityAi_TurnCommand(void *e);
extern void EntityAi_MeleeAttack(void *e);
extern void EntityAi_Guard(void *e);
extern s32 rand(void);
extern u32 frame_counter;
extern u8 player_state[];
extern u8 player_weapon_step[];
extern void *held_item_model_ptr;
extern void *entity_type_handlers[];

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
#ifndef E_SPAWN
#define E_SPAWN        0x10
#endif
#define E_RADIUS       0x38
#define E_HEIGHT       0x3C
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
#define E_MOVE         0xF8
/* bytes propios: Entity+0x170.. (relleno que las preparaciones ponen a cero) */
#define E_PUNTO        0x170           /* x, y, z del punto al que pasea */
#define E_ACCION       0x17C           /* acción en curso: A_* */
#define E_TRAS_GOLPE   0x17D           /* 1: la última acción fue un golpe */
#define E_APARTA       0x17E           /* 1: se está alejando de ti */
/* EntityModel */
#define M_POS_X        0xC0
#define M_POS_Y        0xC4
#define M_POS_Z        0xC8
#define M_ROT_Y        0xD4
#define M_SCALE_X      0xE0
/* EntityParams */
#define P_MAX_SPEED    0x54
#define P_MOTION_IDS   0x60
#define P_GOLPE        0x240
#define BLOQUE         0x3F8
/* EntitySpawnInfo */
#define S_X            0x00
#define S_Z            0x08
#define S_RADIO        0x4C

#define A_NADA    0
#define A_QUIETO  1
#define A_PASEAR  2
#define A_MOVERSE 3
#define A_GUARDIA 4

#define PI_F      3.1415927f
#define DOS_PI    6.2831855f
#define GUARDIA_ANGULO 1.5184364f      /* 87 grados (el del esqueleto del King's Field: 31 x 32 / 4096 vueltas) */

#define ESTADO_LO_VE     2
#define MOVE_FORWARD     0x1
#define MOVE_BACK        0x2
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

/* ángulo entre su frente (más un desvío en grados) y tú */
static f32 angulo_a_ti(void *e, s32 desvio_grados) {
    void *m = P(e, E_MODEL);
    f32 desvio = (f32)desvio_grados * (PI_F / 180.0f);

    if (F(m, M_SCALE_X) < 0.0f) {
        desvio = -desvio;
    }
    return absf(envolver(F(e, E_HEADING) - envolver(F(m, M_ROT_Y) + desvio)));
}

/* peso del golpe i si estás a su alcance (como el King's Field: menos cuanto más lejos), o -1 */
static s32 peso_golpe(void *e, u8 *prm, s32 i) {
    u8 *l = prm + P_GOLPE + 0x88 * i;
    void *m = P(e, E_MODEL);
    f32 d, lejos, cerca, llega, y, py;
    s32 w = B(l, 0);

    if (w == 0) {
        return -1;
    }
    if (!(angulo_a_ti(e, SH(l, 0x0E)) < F(l, 8))) {
        return -1;
    }
    d = F(e, E_DIST);
    lejos = (f32)H(l, 6) + F(e, E_RADIUS) + 100.0f;
    cerca = H(l, 4) ? (f32)H(l, 4) + F(e, E_RADIUS) + 100.0f : 0.0f;
    if (!(d < lejos) || d < cerca) {
        return -1;
    }
    /* a su altura (como EntityAi_PickAttack; y crece hacia abajo) */
    y = F(m, M_POS_Y);
    py = F(player_state, 4);
    if (y < py - 230.0f || y > py + F(e, E_HEIGHT)) {
        return -1;
    }
    llega = F(e, E_RADIUS) + (f32)H(l, 0x30);
    if (d > (llega + lejos) * 0.5f) {
        w = w - w / 3;
    } else if (d > llega) {
        w = w - w / 6;
    }
    return w;
}

/* ¿te está atacando? (como EntityAi_ShouldGuard: el arma en sus primeros fotogramas) */
static s32 atacando(void) {
    void *arma = held_item_model_ptr;
    void *tablas;

    if (player_weapon_step[0] == 0 || arma == 0) {
        return 0;
    }
    tablas = P(arma, 0xFC);
    if (tablas == 0) {
        return 0;
    }
    return SH(tablas, 0x82) < 6;
}

static void empezar_mover(void *e, s32 mando, s32 run_now) {
    u8 *prm = (u8 *)P(e, E_PARAMS);

    W(e, E_FLAGS_LO) &= ~MOTION_STEP_MASK;
    /* los que andan con la animación (la mayoría del IV, velocidad máxima 0) la siguen; los demás se mueven solos */
    if ((mando & (MOVE_FORWARD | MOVE_BACK)) && !(F(prm, P_MAX_SPEED) > 0.0f)) {
        W(e, E_FLAGS_LO) |= MOTION_STEP_MOVE;
    }
    H(e, E_MOVE_CMD) = (u16)mando;
    EntityAi_StartAction(e, (void (*)(void *))P(e, E_MOVE), run_now);
}

static void nuevo_punto(void *e) {
    u8 *sp = (u8 *)P(e, E_SPAWN);
    s32 r = sp ? H(sp, S_RADIO) : 0;

    if (r < 100) {
        r = 500;
    }
    if (sp) {
        F(e, E_PUNTO) = F(sp, S_X) + (f32)(azar(2 * r) - r);
        F(e, E_PUNTO + 8) = F(sp, S_Z) + (f32)(azar(2 * r) - r);
    } else {
        void *m = P(e, E_MODEL);
        F(e, E_PUNTO) = F(m, M_POS_X) + (f32)(azar(2 * r) - r);
        F(e, E_PUNTO + 8) = F(m, M_POS_Z) + (f32)(azar(2 * r) - r);
    }
}

void KF1_Think(void *e, s32 run_now) {
    u8 *prm = (u8 *)P(e, E_PARAMS);
    u8 *k = prm + BLOQUE;
    s32 accion = B(e, E_ACCION), cual = -1, mejor = -1, s, i, mando, lo_ve, sigue;
    s32 frames = B(k, 0x14) ? B(k, 0x14) : 12;
    f32 d;

    if (frame_counter % 10u == (u32)B(e, E_SPAWN_INDEX) % 10u) {
        EntityAi_SensePlayer(e, 2);      /* 2: aunque algo tape la vista, te sigue viendo */
    }
    if (H(e, E_BUSY) != 0) {
        return;
    }
    EntityAi_StepState(e);
    d = F(e, E_DIST);
    lo_ve = SB(e, E_STATE) == ESTADO_LO_VE;

    /* sigue con lo que hacía hasta que se acaba su tiempo (los golpes y la guardia acaban solos) */
    if (accion != A_NADA && accion != A_GUARDIA && H(e, E_ACT_TIMER) != 0) {
        goto hacer;
    }
    /* decidir */
    if (B(k, 2) || B(k, 3)) {
        s = azar(B(k, accion == A_QUIETO ? 3 : 2));
        if (s > mejor) {
            mejor = s;
            cual = 10 + A_QUIETO;
        }
    }
    if (B(k, 4) || B(k, 5)) {
        s = azar(B(k, accion == A_PASEAR ? 5 : 4));
        if (s > mejor) {
            mejor = s;
            cual = 10 + A_PASEAR;
        }
    }
    sigue = accion == A_MOVERSE ? H(k, 0x0E) : H(k, 0x0C);
    if (lo_ve && B(k, 6) && d <= (f32)sigue) {
        s = azar(B(k, 6));
        if (B(e, E_TRAS_GOLPE)) {
            s += s;
        }
        if (s > mejor) {
            mejor = s;
            cual = 10 + A_MOVERSE;
        }
    }
    if (lo_ve && B(k, 8) && d <= (f32)H(k, 0x0A) + F(e, E_RADIUS) && atacando()
        && angulo_a_ti(e, 0) < GUARDIA_ANGULO) {
        s = azar(B(k, accion == A_GUARDIA ? 9 : 8));
        if (s > mejor) {
            mejor = s;
            cual = 10 + A_GUARDIA;
        }
    }
    if (lo_ve && B(e, E_ATK_DELAY) == 0) {
        for (i = 0; i < 3; i++) {
            s32 w = peso_golpe(e, prm, i);
            if (w >= 0) {
                s = azar(w);
                if (s > mejor) {
                    mejor = s;
                    cual = i;
                }
            }
        }
    }
    if (cual >= 0 && cual < 3) {
        W(e, E_FLAGS_HI) = (W(e, E_FLAGS_HI) & ~ATAQUE_MASK) | ((u32)cual << 26);
        B(e, E_ACCION) = A_NADA;
        B(e, E_TRAS_GOLPE) = 1;
        P(e, E_TARGET) = player_state;
        EntityAi_StartAction(e, EntityAi_MeleeAttack, run_now);
        return;
    }
    if (cual == 10 + A_GUARDIA) {
        B(e, E_ACCION) = A_GUARDIA;
        B(e, E_TRAS_GOLPE) = 0;
        EntityAi_StartAction(e, EntityAi_Guard, run_now);
        return;
    }
    accion = cual >= 10 ? cual - 10 : A_QUIETO;
    if (accion == A_PASEAR && B(e, E_ACCION) != A_PASEAR) {
        nuevo_punto(e);
    }
    if (accion == A_MOVERSE) {          /* apartarse, como el "moverse" del King's Field */
        if (B(e, E_ACCION) != A_MOVERSE) {
            B(e, E_APARTA) = B(e, E_TRAS_GOLPE);
        }
        if (d >= (f32)H(k, 0x12)) {
            B(e, E_APARTA) = 0;
        } else if (d <= (f32)H(k, 0x10)) {
            B(e, E_APARTA) = 1;
        }
    }
    B(e, E_ACCION) = (u8)accion;
    B(e, E_TRAS_GOLPE) = 0;
    H(e, E_ACT_TIMER) = (u16)(accion == A_MOVERSE ? frames : 3 * frames);

hacer:
    accion = B(e, E_ACCION);
    if (accion == A_MOVERSE) {
        P(e, E_TARGET) = player_state;
        if (!B(k, 0x15)) {
            empezar_mover(e, EntityAi_TurnCommand(e), run_now);       /* no anda: solo se gira */
        } else if (!B(e, E_APARTA)) {
            empezar_mover(e, EntityAi_TurnCommand(e) | MOVE_FORWARD, run_now);
        } else if (B(prm, P_MOTION_IDS + 5)) {                       /* tiene andar hacia atrás */
            empezar_mover(e, EntityAi_TurnCommand(e) | MOVE_BACK, run_now);
        } else {                       /* sin andar hacia atrás (la mayoría del IV): se queda de cara a ti */
            empezar_mover(e, EntityAi_TurnCommand(e), run_now);
        }
    } else if (accion == A_PASEAR) {
        P(e, E_TARGET) = (u8 *)e + E_PUNTO;
        empezar_mover(e, EntityAi_TurnCommand(e) | MOVE_FORWARD, run_now);
    } else {
        empezar_mover(e, 0, run_now);
    }
}

void KF1_Init(void *e) {
    u8 *prm = (u8 *)P(e, E_PARAMS);
    s32 base = B(prm, BLOQUE);
    void (*init)(void *);

    if (base >= 0x53) {
        base = 5;                      /* el escarabajo */
    }
    init = (void (*)(void *))entity_type_handlers[2 * base];
    init(e);
    P(e, E_THINK) = (void *)KF1_Think_entrada;
    B(e, E_ACCION) = A_NADA;
    B(e, E_TRAS_GOLPE) = 0;
    B(e, E_APARTA) = 0;
}
