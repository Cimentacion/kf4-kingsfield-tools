# -*- coding: utf-8 -*-
"""
kf1_dialogos_en.py - Lo que dice la gente de los niveles 0 y 1 del King's Field, en inglés: el texto original del
disco europeo (CD/COM/TALK0.T, cada línea una imagen), leído con OCR y repasado a mano.

Clave: la línea de TALK0.T. Lo usan los idiomas del juego que no son el castellano (kf1_dialogos_es.py).
"""

DIALOGOS = {
    # --- nivel 0: el pescador de la orilla ---
    90: "You look like the person that was on the ship that wrecked a few days ago, but it's hard to believe that "
        "you were able to make it to shore. Usually when a ship wrecks out there, no one makes it here alive, "
        "except for those who are tradesmen.",
    91: "I came here to look for the Viking's treasures. But this island is filled with poison, and now I can't "
        "live without the water on this island. I cannot leave.",
    92: "See that lighthouse over there? It was made by King Harvine a long time ago. It still works though, as it "
        "is lit by the magic powers of the Mage, Tsedeck. You can easily go over there, if you go through the "
        "shallow waters. But be careful, and watch out for Sigills, the dangerous sea monsters.",
    93: "It's pretty dangerous around here. When you go inside this island, you will see so many monsters. The "
        "Kraken's nest is especially dangerous. Don't go near it.",
    94: "There are some people living on this island, as well as sea merchants. You'd better go explore this "
        "place.",
    95: "The village is behind the wooden door. I think you need special equipment to survive. You have to hurry.",
    96: "You'd better hurry.",
    # --- nivel 1: el barquero (tienda) ---
    60: "Can I help you? I don't have much stuff, but you will need items to be able to walk around this island.",
    61: "Each equipment has its own characteristics, so you must choose your equipment very wisely.",
    62: "I don't have anything which will surprise Gelffy. If you have anything like that, I will buy it from you.",
    63: "You'd better have weapons that fit you. If a weapon is too heavy, you cannot fight very well.",
    64: "I am O.K., but you cannot pass there. There are soldiers at the Base. If you get caught, you have to go "
        "to the jail.",
    65: "I wish Gelffy thought better of me. He thinks I am just a boatsman.",
    66: "Rowing a boat was very tough.",
    67: "Hello. You'd better have enough equipment.",
    68: "Gelffy always told me about Galth Fee. I think Gelffy wants me to find him something special.",
    69: "Seath, the god of High-Elves, didn't give anything to the Dark-Elves.",
    70: "Hello. You'd better have enough equipment.",
    71: "Do you know about the Sword called \"The Spider\"? Don't worry about it if you don't know.",
    72: "I heard that the King of Yerdite is really strong. I wonder what kind of Sword he has.",
    73: "Only Gelffy can go down to the underworld, but I want to go sometime. I heard about the monsters that "
        "spew fire, and I am very interested.",
    74: "I want to make some money, but I don't need very much.",
    75: "Hello. Don't work too hard.",
    # --- nivel 1: Nola ---
    110: "My name is Nola. My brother Dias came to this island two years ago, but we haven't seen each other. If "
         "you see my brother, would you tell him that I am here?",
    111: "Dias came to this island to meet a powerful warrior. I don't know if he wanted to learn something from "
         "him or if he wanted to fight him.",
    112: "I wonder why there is sunlight here, while the other parts of the island are always in the dark. I wish "
         "the whole island were like this.",
    113: "Fai, the man who came here with my brother, has also disappeared. He was a very kind person and our good "
         "friend. How come Fai and my brother don't contact me?",
    114: "Do you know where my brother is?",
    115: "I've noticed that my neighbors are disappearing. I am scared and sad. How can I get off this island?",
    116: "I have hardly seen any visitors here, but I met a man from Yerdite named Earnest. He was captured and "
         "taken by the soldiers.",
    117: "There is a door which has never opened. A picture of Seath is carved on that door.",
    118: "I saw a key on the pedestal of a guidepost. I didn't know who it belonged to, so I left it there.",
    119: "Al came by and told me that a soldier who escaped from the jail said that there was a hidden door inside "
         "of the jail.",
    120: "I want to go back to the good old days.",
    121: "Al told me that Necron is very powerful. If my brother met him, then he has fought with him. I hope my "
         "brother is safe.",
    122: "I want to find my brother as soon as possible.",
    123: "Somebody gives me food sometimes. I saw him from the back. I think it was Fai.",
    124: "Why doesn't Fai come to see me? I will pray to the god of the earth for the safe return of my brother.",
    # --- nivel 1: los del pueblo ---
    320: "Hello newcomer. You can go to the underworld if you want to find some crystals. I cannot go down below "
         "because I'm too fat. Anyway, I have some herbs to sell.",
    321: "I will tell you a secret. The Green Slime can resolve poison, so try to touch its body whenever you are "
         "poisoned.",
    322: "Run away if you see the monsters. Don't even think about fighting them even though you are a skillful "
         "swordsman.",
    323: "I wonder why I'm always so hungry.",
    324: "The Elf merchants are doing business around here, but the things that they sell are pretty expensive. I "
         "have cheaper herbs, but no one wants to buy them. Maybe it's because they are the liquid kind.",
    325: "The bridge's switch is controlled by Necron's soldiers, so people cannot move around frequently.",
    326: "Never go into the door connected to the underworld at Base No. 1. Once you step inside there, you will "
         "die.",
    327: "Can you believe that I was really skinny before?",
    328: "Have you ever heard of the recovering fountain? It was created by the god of High-Elf named Seath.",
    329: "The water and food supply have been overtaken by Necron because the people here did not obey him. But, "
         "we have been able to survive so far. My brother Kehl brings us food, and we drink water at Nola's "
         "place.",
    330: "We haven't had any trouble surviving so far.",
    331: "We cannot go any further because of the monsters, but there is food down in the underworld.",
    332: "We used to move to other villages freely before, but now the passage is locked and tightly guarded... I "
         "hope that nothing terrible happens.",
    333: "I heard that some soldiers have arrived from Yerdite. I think that is the reason for the guards. I wonder "
         "why King Alfred would want this island.",
    334: "Sometimes I see a fellow go over to Nola's place. He doesn't look like a thief or anything, but I would "
         "like to know who he is.",
    335: "You should bring as many herbs as possible.",
    336: "An Elf merchant sometimes visits Kehl's house. They seem to be good friends.",
    337: "Sandler is a naughty boy. I always get into trouble with him, but I haven't seen him in a while.",
    338: "There is a Big Mine and a Small Mine on this island. The Small Mine is on the other side of the bridge. "
         "Anyway, you won't find anything there.",
    339: "They won't let me go across the bridge over there. I want to go over there because Jose is over there, "
         "and that is where the Elf's grandson is doing business.",
    340: "I want to eat something that tastes really good.",
    # --- nivel 1: el soldado escondido ---
    370: "I've never seen you around here. You must be one of the soldiers looking for Necron. He is terribly "
         "strong. I was with him for a long time, but now I am hiding from him.",
    371: "Necron's soldiers don't stop fighting until they die. They have lost their souls and their minds... I'm "
         "very afraid of them.",
    372: "I can't stay on this island anymore. It's so dangerous. I really need the item which would help me to "
         "get off this island. If you bring it to me, I will give you something special.",
    373: "I need the Figure of Seath, known amongst the Elves. If you bring it to me, I will give you the Moon "
         "Gate.",
    # --- nivel 1: los mineros ---
    420: "This is an old tunnel so no more crystals can be found here. The crystal-miners in the central island "
         "have gone down to the underworld to a place called the \"Big Mine.\" They went there to find crystals, "
         "but they looked like they were about to die.",
    421: "I don't know what you're looking for, but you should talk to Harris before going to the Big Mine. He "
         "lives at his friends' graveyard on the eastern part of the island.",
    422: "There are soldiers' Bases on the passage. I don't know how many Bases there are... maybe six. I know "
         "about Base No. 5. It's near the Big Mine.",
    423: "You saw plenty of Slime around here, didn't you? You cannot slash them with a sword. You have to have "
         "something to stick them with or use fire against them.",
    424: "There is a cave made by Elves somewhere down in the underworld. The Elves had hidden there just before "
         "they died. Necron is looking for something down there, so the crystal-miners who received the "
         "\"Day-Light\" are down there digging for it.",
    425: "The monsters around here are called \"Termites.\" Their nest is near the central village. I know there "
         "are some crystals in that nest, but I don't want to go there. No way!",
    426: "You can attack the Termites with a bow. If you have the bow, try to use it against them.",
    427: "I hate those Termites.",
    428: "I want to find the bell that uncle Harris told me about. I haven't been able to find even one piece of "
         "crystal, even though I've been digging a lot.",
    429: "My house is on the south side, but those who live near Al's house on the north side are all dead.",
    430: "I used to see many soldiers from Yerdite here, but now I don't see any. Maybe they were all killed by "
         "Necron or captured by his soldiers.",
    431: "Someone told me there are many crystals on this island. I shouldn't have believed this.",
    432: "I heard that there was a fountain to the north of the Small Mine. I don't think that the water can be "
         "drawn over there.",
    433: "I hope that at least the Termites have gone.",
    # --- nivel 1: el cerrajero ---
    590: "Treasure hunting? There are many treasures that were hidden by Kings and Mages on this island. The "
         "treasure boxes and the doors are all locked, but I can make you any kind of key.",
    591: "Nobody can make keys on this island, except for me.",
    592: "Actually, I hate to tell you this, but I was busted for duplicating a key for Gill the Thief!",
    593: "Don't put my keys to bad use, please.",
    594: "Because Seath granted it, I can duplicate any kind of key.",
    595: "Necron's soldiers always guard the main passage, and the door is locked. You need a key called the "
         "\"Rhombus Key\" to open this door.",
    596: "There's a stairway that goes down to Base No. 1. You must not go down this stairway. Well, I don't think "
         "you can even reach the Base.",
    597: "The Soldiers' Door is locked on both sides. You can only open it on the side where the key is found.",
    598: "I don't have any customers these days.",
    599: "I made a key to the Treasure House of Yerdite for someone. I think I did a pretty good job, so that key "
         "must be useful.",
    600: "You shouldn't stay on this island any longer. But you won't be able to go back to your country because "
         "this island is poisoned.",
    601: "I want to make a strange key someday.",
    602: "I want to make a strange key someday.",
    603: "Dalf told me that there is part of a Castle built by King Harvine, and he showed me \"Harvine's Key\" at "
         "the same time. I wish I could duplicate that key.",
    604: "Do you know about \"the Skull Key\"? Anyway, it is secret.",
    605: "I wonder what Gill is doing now. I think he is stealing something.",
    606: "There is a rumor that there is an Elf Shrine in the underworld. I don't know what it is for, but you need "
         "two keys to get in. I heard that one of those keys was thrown into the ocean. If I had one of these "
         "keys, I could duplicate it.",
    607: "I have collected enough keys, and I want to start treasure hunting. But I am afraid of the monsters.",
    # --- nivel 1: Alexander ---
    620: "I can't imagine why Alexander came to this island. King Alfred's soldiers have almost been wiped out, and "
         "I can't do anything. I have a stone that an Elf gave to the King's Father. Please take it with you.",
    621: "We haven't found the \"King's Sword\" yet. Necron's power is stronger than before, and I think that he "
         "also controls the monsters.",
    622: "The remaining soldiers must be waiting for my help. I have to find them and then try and save them.",
    623: "I hope everyone is still alive.",
}
