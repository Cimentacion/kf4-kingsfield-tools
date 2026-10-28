# -*- coding: utf-8 -*-
"""
kf1_dialogos_es.py - Lo que dice la gente de los niveles 0 y 1 del King's Field, en castellano.

Clave: la línea de TALK0.T (inglés, el disco europeo) que traduce. El juego del IV no tiene ¿ ni ¡ en su fuente:
las preguntas van solo con el signo de cierre, como en sus propios textos.
"""

DIALOGOS = {
    # --- nivel 0: el pescador de la orilla ---
    90: "Pareces el que iba en el barco que naufragó hace unos días. Cuesta creer que llegaras vivo a la "
        "orilla. Cuando un barco se hunde ahí fuera, nadie llega aquí con vida, salvo los mercaderes.",
    91: "Vine a buscar los tesoros de los vikingos. Pero esta isla está llena de veneno y ahora no puedo vivir "
        "sin su agua. No puedo marcharme.",
    92: "Ves aquel faro? Lo hizo el rey Harvine hace mucho tiempo. Aún funciona: lo enciende la magia del mago "
        "Tsedeck. Se llega fácil por los bajíos, pero ten cuidado con los Sigill, los monstruos del mar.",
    93: "Esto es muy peligroso. Cuando entres en la isla verás muchísimos monstruos. El nido del Kraken es lo "
        "peor de todo. No te acerques.",
    94: "En esta isla vive alguna gente, y también hay mercaderes del mar. Más te vale explorarla.",
    95: "El pueblo está detrás de la puerta de madera. Creo que necesitas un equipo especial para sobrevivir. "
        "Date prisa.",
    96: "Más te vale darte prisa.",
    # --- nivel 1: el barquero (tienda) ---
    60: "Te ayudo en algo? No tengo mucho género, pero necesitarás cosas para andar por esta isla.",
    61: "Cada pieza de equipo tiene lo suyo, así que elige bien lo que llevas.",
    62: "No tengo nada que sorprenda a Gelffy. Si tú tienes algo así, te lo compro.",
    63: "Más te vale llevar armas a tu medida. Con un arma demasiado pesada no se lucha bien.",
    64: "Yo estoy bien, pero por ahí no se pasa. En la Base hay soldados. Si te cogen, acabas en la cárcel.",
    65: "Ojalá Gelffy pensara mejor de mí. Para él no soy más que un barquero.",
    66: "Remar era muy duro.",
    67: "Hola. Más te vale ir bien equipado.",
    68: "Gelffy siempre me hablaba de Galth Fee. Creo que quiere que le encuentre algo especial.",
    69: "Seath, el dios de los Altos Elfos, no les dio nada a los Elfos Oscuros.",
    70: "Hola. Más te vale ir bien equipado.",
    71: "Conoces la espada llamada \"La Araña\"? Si no la conoces, no te preocupes.",
    72: "He oído que el rey de Verdite es muy fuerte. Qué espada llevará?",
    73: "Solo Gelffy puede bajar al inframundo, pero algún día quiero ir yo. He oído hablar de monstruos que "
        "escupen fuego y me interesa mucho.",
    74: "Quiero ganar algo de dinero, pero no me hace falta mucho.",
    75: "Hola. No trabajes demasiado.",
    # --- nivel 1: el cerrajero ---
    590: "Buscas tesoros? En esta isla hay muchos, escondidos por reyes y magos. Los cofres y las puertas están "
         "todos cerrados, pero yo te hago la llave que quieras.",
    591: "Nadie más en esta isla sabe hacer llaves.",
    592: "La verdad, no me gusta contarlo, pero me pillaron por copiarle una llave a Gill el Ladrón.",
    593: "No uses mal mis llaves, por favor.",
    594: "Seath me concedió el don de copiar cualquier llave.",
    595: "Los soldados de Necron guardan siempre el paso principal, y la puerta está cerrada. Para abrirla "
         "necesitas la llave llamada \"Llave Rombo\".",
    596: "Hay una escalera que baja a la Base número 1. No bajes por ella. Aunque no creo que llegues a la Base.",
    597: "La Puerta de los Soldados está cerrada por los dos lados. Solo se abre por el lado donde está la llave.",
    598: "Estos días no tengo clientes.",
    599: "Hice una llave de la Casa del Tesoro de Verdite para alguien. Creo que me salió muy bien, así que esa "
         "llave le será útil.",
    600: "No deberías quedarte más en esta isla. Pero tampoco podrás volver a tu país, porque esta isla está "
         "envenenada.",
    601: "Algún día quiero hacer una llave rara.",
    602: "Algún día quiero hacer una llave rara.",
    603: "Dalf me contó que hay parte de un castillo que construyó el rey Harvine, y a la vez me enseñó la "
         "\"Llave de Harvine\". Ojalá pudiera copiarla.",
    604: "Conoces la \"Llave Calavera\"? Bueno, es un secreto.",
    605: "Qué estará haciendo Gill? Seguro que robando algo.",
    606: "Dicen que en el inframundo hay un santuario de los elfos. No sé para qué es, pero hacen falta dos "
         "llaves para entrar. He oído que una la tiraron al mar. Si tuviera una, podría copiarla.",
    607: "Ya tengo bastantes llaves y quiero ponerme a buscar tesoros. Pero me dan miedo los monstruos.",
    # --- nivel 1: Nola ---
    110: "Me llamo Nola. Mi hermano Dias vino a esta isla hace dos años y no nos hemos vuelto a ver. Si lo ves, "
         "le dirás que estoy aquí?",
    111: "Dias vino a esta isla a conocer a un guerrero poderoso. No sé si quería aprender de él o luchar "
         "contra él.",
    112: "Por qué habrá luz del sol aquí, si el resto de la isla está siempre a oscuras? Ojalá toda la isla "
         "fuera así.",
    113: "Fai, el que vino con mi hermano, también ha desaparecido. Era muy buena persona y un buen amigo. Por "
         "qué no dan señales de vida ni Fai ni mi hermano?",
    114: "Sabes dónde está mi hermano?",
    115: "Mis vecinos van desapareciendo. Tengo miedo y estoy triste. Cómo salgo de esta isla?",
    116: "Aquí casi no viene nadie, pero conocí a un hombre de Verdite llamado Earnest. Lo cogieron los "
         "soldados y se lo llevaron.",
    117: "Hay una puerta que nunca se ha abierto. Tiene grabada la imagen de Seath.",
    118: "Vi una llave en el pedestal de un poste indicador. No sabía de quién era, así que la dejé allí.",
    119: "Al vino y me contó que un soldado que se escapó de la cárcel decía que dentro de la cárcel hay una "
         "puerta escondida.",
    120: "Quiero volver a los buenos tiempos.",
    121: "Al me dijo que Necron es muy poderoso. Si mi hermano se encontró con él, habrá luchado. Espero que mi "
         "hermano esté bien.",
    122: "Quiero encontrar a mi hermano cuanto antes.",
    123: "A veces alguien me trae comida. Lo vi de espaldas. Creo que era Fai.",
    124: "Por qué no viene Fai a verme? Rezaré al dios de la tierra para que mi hermano vuelva sano y salvo.",
    # --- nivel 1: el gordo de las hierbas (tienda) ---
    320: "Hola, recién llegado. Si quieres encontrar cristales, puedes bajar al inframundo. Yo no puedo bajar "
         "porque estoy demasiado gordo. En fin, tengo hierbas para vender.",
    321: "Te cuento un secreto. El Limo Verde cura el veneno, así que tócale el cuerpo cuando estés "
         "envenenado.",
    322: "Si ves a los monstruos, huye. Ni se te ocurra luchar con ellos, por muy buen espadachín que seas.",
    323: "Por qué tendré siempre tanta hambre?",
    324: "Los mercaderes elfos andan por aquí, pero lo que venden es bastante caro. Mis hierbas son más "
         "baratas, pero nadie las quiere. Será porque son de las líquidas.",
    325: "El interruptor del puente lo controlan los soldados de Necron, así que la gente no puede ir y venir "
         "como antes.",
    326: "Nunca entres por la puerta que lleva al inframundo en la Base número 1. Si pisas dentro, mueres.",
    327: "Te puedes creer que antes estaba flaco?",
    328: "Has oído hablar de la fuente que cura? La creó el dios de los Altos Elfos, Seath.",
    329: "Necron se quedó con el agua y la comida porque la gente de aquí no le obedeció. Pero hasta ahora hemos "
         "aguantado. Mi hermano Kehl nos trae comida y bebemos agua en casa de Nola.",
    330: "Hasta ahora no nos ha costado sobrevivir.",
    331: "No podemos ir más allá por los monstruos, pero abajo, en el inframundo, hay comida.",
    332: "Antes íbamos de un pueblo a otro sin problemas, pero ahora el paso está cerrado y muy vigilado... "
         "Espero que no pase nada malo.",
    333: "He oído que han llegado soldados de Verdite. Creo que por eso hay guardias. Para qué querrá el rey "
         "Alfred esta isla?",
    334: "A veces veo a un tipo ir a casa de Nola. No parece un ladrón ni nada de eso, pero me gustaría saber "
         "quién es.",
    335: "Llévate todas las hierbas que puedas.",
    336: "Un mercader elfo visita a veces la casa de Kehl. Parecen buenos amigos.",
    337: "Sandler es un niño travieso. Siempre me mete en líos, pero hace tiempo que no lo veo.",
    338: "En esta isla hay una Mina Grande y una Mina Pequeña. La pequeña está al otro lado del puente. "
         "Aunque allí no vas a encontrar nada.",
    339: "No me dejan cruzar ese puente. Quiero ir al otro lado, porque allí está Jose, y allí tiene su negocio "
         "el nieto del elfo.",
    340: "Quiero comer algo que sepa muy bien.",
    # --- nivel 1: Fai, escondido ---
    370: "Nunca te había visto por aquí. Debes de ser uno de los soldados que buscan a Necron. Es terriblemente "
         "fuerte. Estuve con él mucho tiempo, pero ahora me escondo de él.",
    371: "Los soldados de Necron no dejan de luchar hasta que mueren. Han perdido el alma y el juicio... Me dan "
         "mucho miedo.",
    372: "No puedo quedarme más en esta isla. Es demasiado peligrosa. Necesito de verdad algo que me ayude a "
         "salir de aquí. Si me lo traes, te daré algo especial.",
    373: "Necesito la Figura de Seath, conocida entre los elfos. Si me la traes, te daré la Puerta de la Luna.",
    # --- nivel 1: el caballero de Verdite ---
    620: "No me imagino por qué vino Alexander a esta isla. Los soldados del rey Alfred casi han desaparecido y "
         "no puedo hacer nada. Tengo una piedra que un elfo le dio al padre del rey. Llévatela, por favor.",
    621: "Aún no hemos encontrado la \"Espada del Rey\". El poder de Necron es más fuerte que antes, y creo que "
         "también controla a los monstruos.",
    622: "Los soldados que quedan deben de estar esperando mi ayuda. Tengo que encontrarlos e intentar "
         "salvarlos.",
    623: "Espero que todos sigan vivos.",
    # --- nivel 1: el minero ---
    420: "Este es un túnel viejo: aquí ya no quedan cristales. Los mineros de la isla central han bajado al "
         "inframundo, a un sitio llamado la \"Mina Grande\". Fueron a buscar cristales, pero tenían cara de "
         "estar a punto de morir.",
    421: "No sé qué buscas, pero deberías hablar con Harris antes de ir a la Mina Grande. Vive en el cementerio "
         "de sus amigos, en el este de la isla.",
    422: "En el paso hay bases de soldados. No sé cuántas... quizá seis. Conozco la Base número 5. Está cerca "
         "de la Mina Grande.",
    423: "Por aquí habrás visto muchos limos, verdad? Con la espada no se les puede cortar. Hace falta algo "
         "para pincharlos, o usar fuego contra ellos.",
    424: "En algún sitio del inframundo hay una cueva hecha por los elfos. Los elfos se escondieron allí "
         "justo antes de morir. Necron busca algo ahí abajo, así que los mineros que recibieron la \"Luz del "
         "Día\" están cavando allí.",
    425: "Los monstruos de por aquí se llaman \"Termitas\". Su nido está cerca del pueblo central. Sé que en "
         "ese nido hay cristales, pero no pienso ir. Ni loco!",
    426: "A las termitas se las puede atacar con arco. Si tienes uno, pruébalo con ellas.",
    427: "Odio a esas termitas.",
    428: "Quiero encontrar la campana de la que me habló el tío Harris. No he encontrado ni un trocito de "
         "cristal, y eso que he cavado mucho.",
    429: "Mi casa está en el lado sur, pero los que vivían cerca de la casa de Al, en el norte, han muerto "
         "todos.",
    430: "Antes veía aquí a muchos soldados de Verdite, pero ahora no veo ninguno. A lo mejor Necron los mató "
         "a todos, o sus soldados los cogieron.",
    431: "Alguien me dijo que en esta isla hay muchos cristales. No debí creérmelo.",
    432: "He oído que al norte de la Mina Pequeña hay una fuente. No creo que de allí se pueda sacar agua.",
    433: "Ojalá al menos se hayan ido las termitas.",
}
