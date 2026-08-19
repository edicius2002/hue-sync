# Modos de efecto, ahora mismo

Inventario para quien mira las luces, no para quien lee el codigo.

> **Parcialmente superado.** La descripcion de `spectrum` esta al dia. El
> resto del documento es anterior a dos cambios: se retiraron `bars`,
> `beat_flash` y `harmony_energy` por redundantes, y `dual`/`roles` nunca
> llegaron a `main` —la configuracion real es `channel_modes`—. Falta ademas
> `wash`. Las secciones de esos modos se conservan como registro de lo que
> se midio, no como inventario de lo que hay.

Hay **seis** looks en `main` y se pueden usar hoy: `combo`, `harmony`,
`spectrum`, `sustain`, `wash` e `idle`.

El modo por defecto es `combo`. Si no pasas `--mode` y no tocas
`config.yaml`, eso es lo que corre.

Todos los comandos de abajo asumen CMD de Windows y el entorno del proyecto.
Los de `main` se lanzan desde la copia que usas a diario:

```bat
cd /d D:\Work\research\hue
```

Cuando no suena nada (~2 s de silencio) **cualquier** modo se apaga a un
naranja tenue (`idle`). No es un fallo: es el reposo. Al volver el audio,
regresa el modo que elegiste.

En la consola, `LOCK` significa que hay pulso. `compas -` y `bconf` bajo
significan que no hay "1" de compas. Sobre `summer.wav` el compas **no
engancha** (confianza 0.046, umbral 0.14). Eso no tumba el ritmo; tumba
lo que depende del compas, sobre todo `bars`.

---

## Tabla resumen

| Modo | Que hace (lo que ves) | Como se usa | Estado |
|---|---|---|---|
| `combo` | Color segun graves/medios/agudos, brillo al beat. Las dos luces iguales. | `run.py sync` (es el default) o `--mode combo` | **En `main`.** Listo. |
| `harmony` | Color del acorde, brillo casi fijo. No parpadea con la bateria. | `--mode harmony` | **En `main`.** Listo, pero en pop/house denso se cae a color de espectro. |
| `bars` | Un color por compas, brillo al beat. Se ve el 4x4. | `--mode bars` | **En `main`.** Listo, pero **sin compas parece `combo`**. En summer.wav no engancha. |
| `beat_flash` | Mismo naranja de reposo, destella en cada beat. | `--mode beat_flash` | **En `main`.** Listo. El mas simple, el menos musical. |
| `spectrum` | Salta entre rojo, magenta y azul segun el espectro. Sin ritmo. | `--mode spectrum` | **En `main`.** Listo. No sigue el beat. |
| `sustain` | Como `combo`, pero en pads/cuerdas deja de destellar y respira. | `--mode sustain` | **En `main`.** Recien calibrado con summer.wav y billie.wav. |
| `idle` | Naranja tenue y fijo. Nunca apagado del todo. | `--mode idle`, o automatico en silencio | **En `main`.** Listo. No es un show, es "sigo vivo". |
| `dual` | Pared = pulso (`combo`). Techo = acorde (`harmony`). | `--mode dual` **en `feat/n-canales`**, no en `main` | **En `feat/n-canales`, sin mergear.** El nombre **va a desaparecer**: se esta pasando a `roles`. |

---

## Como elegir el modo (los tres sitios)

1. Un shot, sin tocar ficheros:

   ```bat
   .\.venv\Scripts\python.exe run.py sync --mode harmony
   ```

2. Dejarlo fijo en `config.yaml`, clave `effects.mode`.

3. Pisar desde el entorno:

   ```bat
   set HUEBPM_EFFECTS_MODE=sustain
   .\.venv\Scripts\python.exe run.py sync
   ```

   `sync` imprime al arrancar lo que vino del entorno. Un nombre mal escrito
   falla en voz alta, no se ignora.

Para ver el efecto en consola, sin luces:

```bat
.\.venv\Scripts\python.exe run.py sync --dry-run --mode combo
```

Cierra Hue Sync: las dos apps no pueden tener la misma area a la vez.

---

## `combo` — el de cada dia

**Que ves.** El color se mueve con lo que suena (graves tirando a rojo,
agudos a azul) y el brillo pega en el beat, un poco antes del golpe, no
despues. Un redoble o una palma a contratiempo blanquea un instante. Las
dos luces hacen lo mismo.

**De que vive.** Pulso (tiene que enganchar el BPM), bandas de frecuencia,
onsets fuera de tiempo. El "1" del compas pega un poco mas fuerte **solo
si el compas engancha**. Si no, todos los beats pesan igual: sigue
habiendo ritmo, solo que mas plano.

**Cuando decepciona.**

* Sin pulso claro (`buscando` en consola): se queda en un brillo bajo y
  no destella. El color sigue al timbre.
* Percusion sola: el color salta con cada golpe de bombo/caja, no con
  acordes. Es el diseno, no un fallo.
* Tempos altos: el destello se lee mas agresivo. El suelo de brillo
  (`beat_floor: 0.12`) evita que se apague del todo entre golpes.
* En summer.wav el compas no engancha: no vas a notar el acento del "1".
  El beat si.

**Como se prueba.**

```bat
cd /d D:\Work\research\hue
.\.venv\Scripts\python.exe run.py sync --mode combo
```

**Estado.** En `main`. Es lo que corre si no eliges nada.

**Parametros que importan.** `beat_attack`, `beat_decay`, `beat_floor`,
`bass_color` / `mid_color` / `treble_color`, `onset_accent`,
`onset_flash`, `onset_decay`, `downbeat_accent` (solo con compas),
`saturation_boost`.

---

## `harmony` — el del acorde

**Que ves.** La luz se queda en un color mientras dura el acorde y cambia
cuando cambia la armonia. Por defecto **no parpadea** con el beat: el
brillo es fijo. Si la mezcla no tiene notas claras, no se inventa un
tono: se pinta con el color de espectro (graves/medios/agudos) y se queda
asi, brillante y sin pulso.

**De que vive.** Armonia (notas) y una medida de "hay tono de verdad o
es ruido/bateria". No necesita compas. El pulso esta apagado a proposito
(`harmony_beat_depth: 0.0`).

**Cuando decepciona.**

* Pop, house, mezcla densa: la tonalidad se queda en 0.03-0.04 y el umbral
  para fiarse es 0.08. Ahi **no hay armonia que seguir** y ves color de
  espectro a brillo lleno, sin destello. Parece una lampara que cambia de
  tono con el timbre, no un modo de acordes.
* Bateria sola, aplausos, ruido: mismo respaldo. Mejor eso que un color
  aleatorio que salta en cada golpe.
* Si le subes pulso a mano, a tempos altos parpadea; el limite de salto
  por frame (`harmony_max_step: 0.03`) esta para cortarlo.

**Como se prueba.**

```bat
cd /d D:\Work\research\hue
.\.venv\Scripts\python.exe run.py sync --mode harmony
```

Pruebalo con algo tonal y despejado (piano, pad, progresion clara). Con
billie.wav o house denso no es el modo.

**Estado.** En `main`.

**Parametros que importan.** `harmony_min_tonality` (0.08),
`harmony_full_tonality` (0.20), `harmony_saturation`,
`harmony_beat_depth` (0 = sin pulso), `harmony_max_step`. El respaldo
usa los colores de banda.

---

## `bars` — el del 4x4

**Que ves.** Cuando el compas engancha, cada compas tiene un color de
una paleta de cuatro (rojo, naranja, verde, azul) y el brillo sigue el
beat. Cada cuatro compases la paleta vuelve a empezar. Se lee la
estructura, no solo el metronomo.

**De que vive.** Compas y frase (`BarTracker`), mas pulso, bandas y
onsets. **Si el compas no engancha, cae a color de espectro con brillo
de beat**: o sea, se ve como `combo`. No rota paleta a lo loco porque
eso se ve peor que no rotarla.

**Cuando decepciona.**

* **summer.wav: el compas no engancha** (0.046 < 0.14). En ese tema
  `bars` **es `combo` con otro nombre**. No es que este roto; no hay
  "1" que detectar.
* House four-on-the-floor, donde el bombo pesa igual en los cuatro
  tiempos: misma historia.
* Aunque enganche, a veces el "1" y el "3" empatan. El cambio de color
  puede caer medio compas corrido. Sigue siendo ritmico; no es el 4x4
  exacto de la partitura.
* En consola: si `compas` es `-`, estas en el respaldo. Si sale `1/4?`
  (con interrogacion), la rejilla esta pero el "1" es dudoso.

**Como se prueba.**

```bat
cd /d D:\Work\research\hue
.\.venv\Scripts\python.exe run.py sync --mode bars
```

Mira `bconf` y `compas` en la linea de estado. Si no suben, no estas
viendo `bars` de verdad.

**Estado.** En `main`. La feature extra (paleta por compas) es la mas
fragil de las siete.

**Parametros que importan.** `phrase_palette`, `downbeat_accent`, mas
los de `combo` para el brillo. El umbral de enganche es
`analysis.downbeat_min_confidence: 0.14`.

---

## `beat_flash` — el metronomo

**Que ves.** Un solo color (el naranja de reposo) que destella en cada
beat. Un golpe fuera de tiempo lo blanquea un momento. No hay graves ni
acordes: es un click visual.

**De que vive.** Pulso y onsets. El acento del "1" solo si hay compas.
El color es `idle_color`: si cambias el naranja de reposo, cambias
tambien este modo.

**Cuando decepciona.**

* Sin pulso: se queda tenue y fijo, como un `idle` un poco mas brillante
  (`beat_floor`).
* En un tema rico se siente pobre: hay musica y la luz solo hace tic-tac.
* Es el que mas se parece a un estrobo. No lo dejes con `beat_floor` a 0.

**Como se prueba.**

```bat
cd /d D:\Work\research\hue
.\.venv\Scripts\python.exe run.py sync --mode beat_flash
```

Sirve para calibrar a ojo si el destello cae **en** el beat
(`latency_compensation_ms`, hoy 120 ms, aun no medido contra las luces).

**Estado.** En `main`.

**Parametros que importan.** `idle_color`, `beat_attack`, `beat_decay`,
`beat_floor`, `onset_accent` / `onset_flash` / `onset_decay`,
`downbeat_accent`.

---

## `spectrum` — los tres colores fuertes

**Que ves.** Un color de tres —rojo, magenta o azul— que salta segun donde
caiga el peso del espectro, con el brillo siguiendo a la energia. **No hay
beat.** Un pad estable se queda quieto; un drop se enciende. Las dos luces
iguales.

No mezcla bandas: ELIGE. Promediar graves, medios y agudos por peso da marron
mucho mas a menudo que rojo, porque tres colores sumados tiran al gris. Medido
sobre los ocho WAV, el color cambia 1.47 veces por segundo de media.

**De que vive.** Solo bandas de frecuencia, a traves del escalon que publica
`SpectrumStep`. No necesita pulso, armonia ni compas.

**Cuando decepciona.**

* Si lo que quieres es ritmo: no lo hay. Un 4/4 claro se ve como un color
  que cambia con la mezcla, no con el bombo.
* Material muy cargado de graves: se queda mucho rato en un solo color.
  Medido, kobosil pasa el 74.6% del tiempo en rojo y baja a 0.41 cambios por
  segundo, un color cada 2.5 s.
* Mastering muy comprimido: las bandas se mueven poco y el escalon no salta.
* Silencio: igual que los demas, cae a `idle`. El escalon se congela en vez de
  reelegir, para que la luz no salte de color al volver el audio.

**Como se prueba.**

```bat
cd /d D:\Work\research\hue
.\.venv\Scripts\python.exe run.py sync --mode spectrum
```

**Estado.** En `main`.

**Parametros que importan.** `spectrum_palette` (los tres colores),
`spectrum_step_edges`, `spectrum_step_tau`, `spectrum_step_margin` y
`spectrum_step_dwell` (cuando cambia), y `beat_floor` (aqui es el suelo de
energia, no de beat).

`bass_color`, `mid_color`, `treble_color` y `saturation_boost` **ya no le
afectan**: viven en `spectrum_color()`, que ahora solo usan `combo`,
`harmony` y `sustain`. Para el brillo por canal, ver `capa-de-salida.md`.

---

## `sustain` — destello que se aplaca en los pads

**Que ves.** En bateria seca, destella como `combo`. Cuando entra un
pad, cuerdas u organo (sonido que se sostiene y ademas tiene notas), el
destello se aplaca y la luz respira. El color sigue siendo el del
espectro, no el del acorde.

**De que vive.** Pulso, bandas, y dos medidas a la vez: "la envolvente
es estable" y "hay tono, no es ruido". Si falta cualquiera de las dos,
sigue destellando. **No pinta onsets** (un redoble no blanquea). No
necesita compas para lo suyo; el acento del "1" solo aparece si el
compas engancha, igual que en `combo`.

**Calibracion reciente (verificada en `config.yaml` y en los comentarios
de `config.py`).** Ya no son los umbrales provisionales 0.35/0.65.

* Sostenimiento: rampa **0.55 .. 0.95**. En material real el detector
  vive entre 0.63 y 0.99; con 0.35/0.65 la mitad de las muestras
  saturaban y se veia un interruptor, no una mezcla.
* Puerta tonal: **0.03 .. 0.045**. El 0.03 no se toca: el peor ruido de
  banda ancha midio 0.0228. El techo bajo a 0.045 para que la puerta
  sea un veto, no la senal que mueve el brillo.
* **summer.wav:** mezcla activa el **60.1%** del tiempo (el tramo con
  pad). **billie.wav: 0.0%** — tema percusivo, es la respuesta correcta.
* Aviso medido: la tonalidad de summer.wav recorre 0.020..0.073 y **se
  solapa** con el maximo del ruido. En mezcla densa esta puerta no
  separa musica de ruido de banda ancha; solo cubre el caso claro.
* El detector de energia (ventana 2.5 s, CV 0.20..0.43) cubre el 87.9%
  de summer.wav y el 0% de billie.wav. Puede confundir compresion de
  mastering con "textura sostenida". Eso aun hay que verlo en las luces.

**Cuando decepciona.**

* billie.wav, rock seco, house con bombo a cada negra: **no vas a notar
  este modo**. Se ve como `combo` sin el blanqueo de onsets.
* Cama de ruido, aplausos, hiss: la puerta tonal deberia dejarlo
  destellando. Si un pad producido es muy denso y poco "tonal", tambien
  puede no abrir.
* summer.wav sin paleta de `bars`: aqui si deberia verse la diferencia,
  en el tramo sostenido.

**Como se prueba.**

```bat
cd /d D:\Work\research\hue
.\.venv\Scripts\python.exe run.py sync --mode sustain
```

Compara el mismo pasaje de summer.wav en `combo` y en `sustain`: en
`combo` sigue destellando; en `sustain` deberia aquietarse.

**Estado.** En `main`. Recien calibrado contra esos dos WAV. Listo para
usar; el riesgo conocido es la compresion y el solape tonal con ruido.

**Parametros que importan.** `sustain_min` (0.55), `sustain_full` (0.95),
`sustain_min_tonality` (0.03), `sustain_full_tonality` (0.045),
`sustain_max_step` (0.03), mas los de beat y color de `combo`. No
comparten umbral con `harmony`: alli la tonalidad pinta el color, aqui
decide el brillo.

---

## `idle` — reposo

**Que ves.** Naranja muy tenue, fijo. Nunca negro. Sirve para no
confundir "no suena nada" con "la app se colgo".

**De que vive.** Nada. Ignora beat, espectro y armonia.

**Cuando decepciona.** Si lo dejas puesto a proposito mientras suena
musica, las luces no hacen show. Eso es lo que pediste.

**Como se prueba.**

```bat
cd /d D:\Work\research\hue
.\.venv\Scripts\python.exe run.py sync --mode idle
```

Para ver el automatico: pon cualquier otro modo, pausa la musica dos
segundos.

**Estado.** En `main`.

**Parametros que importan.** `idle_color`, `idle_brightness` (0.07).
Ojo: `idle_color` tambien es el color de `beat_flash`.

---

## `dual` — dos luces, dos oficios (nombre en via de extincion)

**Que ves.** Con exactamente dos luces bien asignadas: la de la **pared
izquierda** destella con el beat y el timbre (`combo`); la del **techo**
se queda en el color del acorde, sin parpadeo (`harmony`). En un cuarto
pequeno eso se lee como "el golpe al lado, el ambiente arriba".

Si el area no tiene dos canales, o si los IDs de pared/techo no son el
par `{0, 1}`, **todo se pinta como `combo`** (las dos luces iguales) y
`sync` avisa en consola.

**De que vive.** Lo mismo que `combo` en la pared y que `harmony` en el
techo. El techo hereda el fallo de `harmony` en mezcla densa (color de
espectro, brillo lleno). El acento de compas, solo en la pared, y solo
si el compas engancha. **No depende del compas para existir.**

**Cuando decepciona.**

* **No esta en `main`.** Desde `D:\Work\research\hue` (copia de `main`),
  `--mode dual` responde `Modo desconocido`.
* Los numeros `wall_channel` / `ceiling_channel` son el **orden en que
  anadiste las luces al area**, no "izquierda" ni "arriba". Si los
  tienes al reves, el techo destella y la pared se queda en color
  quieto: se ve mal y cansa. Identifica cada luz a ojo antes de
  asignarlos.
* Una sola luz, o tres: cae a `combo` en todas. No reparte roles.
* En pop/house el techo no va a "seguir el acorde"; va a lavar en
  espectro. La pared si seguira el beat.

**Como se prueba.** No desde `main`. Desde esta rama (`feat/n-canales`),
con el Python del entorno de siempre:

```bat
cd /d D:\Work\research\hue\.ccb\workspaces\worker3
D:\Work\research\hue\.venv\Scripts\python.exe run.py sync --mode dual
```

Si `wall_channel` y `ceiling_channel` estan cruzados, inviertelos en
`config.yaml` y vuelve a lanzar. No hay deteccion geometrica.

**Estado.** En `feat/n-canales`, **sin mergear y sin PR**. Existe y
tiene tests. **El nombre `dual` se esta sustituyendo por `roles`**
(lista de roles para N luces, no solo el par pared/techo). No memorices
`dual` ni lo dejes escrito como el modo de cada dia: va a dejar de
existir.

**Parametros que importan.** `wall_channel` (0), `ceiling_channel` (1),
mas todo lo de `combo` y `harmony`.

---

## Dependencia del compas, en corto

`BarTracker` (el "1" del compas) **no es un modo**. Es un enganche
aparte del BPM. Umbral de entrada: 0.14. En summer.wav: 0.046.

| Modo | Que pierde si el compas no engancha |
|---|---|
| `bars` | **Lo que lo distingue.** Se ve como `combo`. |
| `combo`, `beat_flash`, `sustain`, pared de `dual` | Solo el acento extra del "1". El beat sigue. |
| `harmony`, `spectrum`, `idle`, techo de `dual` | Nada. No lo usan. |

---

## Que probar primero con estas dos luces

Pared izquierda + techo, cuarto pequeno.

**Hoy, desde `main`:** `combo`. Es el que ya tienes, las dos luces van a
la par, y en este cuarto un solo color llena el volumen sin pelearse.
`harmony` a solas deja el techo y la pared sin pulso; `bars` en
summer.wav no te va a mostrar el 4x4; `beat_flash` se queda corto;
`sustain` solo se nota en el tramo de pad.

**En cuanto quieras el contraste lateral/cenital:** el efecto que
encaja es el de `dual` (pared = pulso, techo = acorde). Pero **no esta
en `main`** y **el nombre se muere**. Cuando aterrice como `roles`, ese
es el primero que yo pondria en este cuarto. Hasta entonces, no inviertas
habito en `--mode dual`.
