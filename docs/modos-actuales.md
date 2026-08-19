# Modos de efecto, ahora mismo

Inventario para quien mira las luces, no para quien lee el codigo.

Hay **seis** looks en `main` y se pueden usar hoy: `combo`, `harmony`,
`spectrum`, `sustain`, `wash` e `idle`. Los seis se pueden asignar por canal
con `channel_modes`; no hay ningun modo especial para "dos luces".

`bars`, `beat_flash` y `harmony_energy` se retiraron por redundantes, y `dual`
nunca llego a `main`. Lo que se midio para descartarlos vive en
`modos-redundantes.md` y `coordinacion-dos-focos.md`.

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
engancha** (confianza 0.046, umbral 0.14). Eso no tumba el ritmo: de los seis
looks vivos, ninguno depende del compas para funcionar. Solo se pierde el
acento extra del "1" en los que llevan envolvente de beat.

---

## Tabla resumen

| Modo | Que hace (lo que ves) | Como se usa | Estado |
|---|---|---|---|
| `combo` | Color segun graves/medios/agudos, brillo al beat. Las dos luces iguales. | `run.py sync` (es el default) o `--mode combo` | **En `main`.** Listo. |
| `harmony` | Color del acorde, brillo casi fijo. No parpadea con la bateria. | `--mode harmony` | **En `main`.** Listo, pero en pop/house denso se cae a color de espectro. |
| `spectrum` | Salta entre rojo, magenta y azul segun el espectro. Sin ritmo. | `--mode spectrum` | **En `main`.** Listo. No sigue el beat. |
| `sustain` | Como `combo`, pero en pads/cuerdas deja de destellar y respira. | `--mode sustain` | **En `main`.** Calibrado con summer.wav y billie.wav. |
| `wash` | Un solo color naranja que sube y baja con la energia. Sin ritmo. | `--mode wash` | **En `main`.** El mas abrupto: depende del recorte de salida, no de suavidad propia. |
| `idle` | Naranja tenue y fijo. Nunca apagado del todo. | `--mode idle`, o automatico en silencio | **En `main`.** Listo. No es un show, es "sigo vivo". |

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
* summer.wav: aqui si deberia verse la diferencia, en el tramo sostenido.

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

## `wash` — un solo color que respira

**Que ves.** Un unico naranja —el mismo de `idle`— cuyo brillo sube y baja
con la energia. **No hay ritmo ni cambio de color.** Es el intermedio entre
`idle`, que es plano, y `spectrum`, que cambia de matiz.

**De que vive.** Solo la energia de la banda mas fuerte. Ignora pulso,
armonia y compas.

**Por que un color fijo.** Dos matices distintos se suman a marron sobre las
paredes de un cuarto pequeno. Reutilizar `idle_color` deja un color estable
mientras el movimiento sigue estando en el brillo.

**Es el look mas abrupto de los seis.** Como el color es fijo,
`max(RGB) = nivel`, asi que transmite el salto de energia entero sin
amortiguarlo. Medido a 50 fps tras el warmup, billie llega a 0.65 de salto por
frame y summer a 0.31. No tiene suavidad propia: depende del recorte de la
capa de salida. Si lo pones en una luz que te llene la periferia visual,
declarala como `ceiling_channel`.

**Cuando decepciona.**

* Material muy comprimido: en summer.wav se satura casi todo el tiempo
  (brillo medio 0.925, minimo 0.825, CV 0.036) y degenera visualmente en un
  `idle` brillante. Es cuestion de calibrar `beat_floor`, no del color fijo.
* Si esperas ver "que" suena: no lo dice. Solo dice cuanto.

**Como se prueba.**

```bat
cd /d D:\Workesearch\hue
.\.venv\Scripts\python.exe run.py sync --mode wash
```

**Estado.** En `main`.

**Parametros que importan.** `idle_color` (el color), `beat_floor` (el suelo
de energia). Comparte los dos con `idle`, asi que cambiarlos mueve ambos.

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
Ojo: `idle_color` tambien es el color de `wash`.

---

## Dependencia del compas, en corto

`BarTracker` (el "1" del compas) **no es un modo**. Es un enganche
aparte del BPM. Umbral de entrada: 0.14. En summer.wav: 0.046.

| Modo | Que pierde si el compas no engancha |
|---|---|
| `combo`, `sustain` | Solo el acento extra del "1". El beat sigue. |
| `harmony` | Solo el acento del "1", si le subiste `harmony_beat_depth`. |
| `spectrum`, `wash`, `idle` | Nada. No lo usan. |

Ningun look vivo se queda sin identidad por falta de compas. Eso era justo lo
que hundia a `bars`, y parte de por que se retiro.

---

## Que probar primero con estas dos luces

Pared izquierda + techo, cuarto pequeno.

**Con un solo look en las dos luces:** `combo`. Es el default, las dos van a
la par, y en este cuarto un solo color llena el volumen sin pelearse.
`harmony` a solas deja ambas sin pulso; `sustain` solo se nota en el tramo de
pad; `wash` degenera en un `idle` brillante sobre material comprimido.

**Para el contraste lateral/cenital**, que es lo que de verdad luce con dos
luces, ya no hace falta un modo aparte: se asigna un look a cada canal.

```yaml
channel_modes: [combo, spectrum]
```

Pared con `combo`, que pulsa al beat; techo con `spectrum`, que aguanta un
color fuerte y estable de fondo. El orden es el `channel_id` del bridge, o sea
el ORDEN EN QUE ANADISTE LAS LUCES AL AREA: averigua cual es cual con
`run.py identify` antes de asignar.

El brillo de cada canal se ajusta aparte, en la capa de salida. Como hacerlo
—y por que `channel_range` no se comporta como una ganancia— esta en
`capa-de-salida.md`.
