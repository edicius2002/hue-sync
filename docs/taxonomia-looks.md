# Taxonomia de looks

Un modo tiene que ser un LOOK: una responsabilidad clara, aplicable a
cualquier canal. Hoy eso no se cumple. `roles` no es un look: fija el par
`combo`+`harmony` (con alias `pulso`/`armonia`) y solo deja poner 4 de los
8 nombres en un canal. `bars`, `beat_flash` e `idle` no se pueden asignar.

Setup unico: canal 0 = pared izquierda (acento local). Canal 1 = techo
(ambiente, llena el cuarto y la periferia visual). Un look en el techo no
puede saltar mas de **0.03 de brillo por frame** a 50 fps.

Los efectos son funciones puras de `RenderContext`. Ningun hueco de esta
nota pide memoria en el efecto: si algo hay que suavizar, ya vive en
`AudioState` (`bands`, `tonality`, `sustain`, `last_onset_time`).

`docs/modos-actuales.md` y `docs/modos-redundantes.md` no estan en este
checkout (`main` @ 5b8cd00). Los numeros de overlap que el encargo da por
buenos (83.2% `bars`=`combo` en summer.wav; `harmony` y `spectrum` misma
receta de color) coinciden con lo que midio esa ronda y con las rutas de
degradacion del codigo. `docs/dos-luces.md` si esta; donde choca con este
requisito, se dice abajo.

---

## 1. Tres ejes

**Color:** de donde sale el RGB, antes de escalar por brillo.

* `espectro` — mezcla graves/medios/agudos (`spectrum_color`)
* `armonia` — `chroma_hue` con saturacion por `tonality` (`harmony_color`)
* `paleta` — `phrase_palette` indexada por el compas
* `fijo` — `idle_color`

**Brillo:** que escala ese RGB.

* `pulso` — `beat_envelope` (pico, anticipa el golpe) + `onset_accent`
* `energia` — max(graves, medios, agudos), suelo `beat_floor`
* `suave` — `gentle_brightness`, cota `max_step` (0.03). Con profundidad 0
  es constante 1.0
* `sostenido` — mezcla `pulso` → `suave` segun `sustain_mix`
* `fijo` — `idle_brightness` (0.07)

**Enganche:** que tiene que ser verdad para no caer a la ruta de degradacion.
El reloj de beat, el compas y la tonalidad fallan en sitios distintos.
summer.wav: compas 0.046 < 0.14; tonalidad ~0.04 < 0.08. billie.wav: mezcla
de sustain 0.0%.

Acento de onset (blanqueo a blanco) no es un cuarto eje: es un extra de
**color** encima del pulso. Lo tienen `combo`, `bars` y `beat_flash`. No lo
tienen `harmony`, `spectrum`, `sustain` ni `idle`. En el techo es un flash
mas: no es cenital-seguro.

Salto de brillo por frame, medido a 120 BPM / 50 fps (el numero del
contrato de `roles`, `config.yaml` y `tests/test_effects_roles.py`):

| fuente de brillo | salto | techo |
|---|---:|---|
| `pulso` (`beat_envelope`) | **0.336** (11x la cota) | no |
| `sostenido` con mezcla 0 | **0.336** (es `pulso`) | no |
| `suave` (`harmony_max_step`) | **0.030** | si |
| `harmony` con depth 0 (default) | **0.000** | si |
| `energia` / `spectrum` (sin pulso) | **0.000*** | si |
| `fijo` / `idle` | **0.000** | si |

\* `spectrum` no usa el reloj: no hay estrobo a 2 Hz. Un drop de energia
puede mover el brillo (el ataque de banda es 5 ms), pero no es el patron
fotosensible del beat. Se marca apto.

---

## 2. Tabla: un look, tres ejes, degradacion, techo

| Look | Color | Brillo | Enganche | Degrada a | Techo | Responsabilidad |
|---|---|---|---|---|---|---|
| `combo` | espectro + blanqueo onset | pulso | reloj | brillo = `beat_floor`, color sigue el timbre | **no** (0.336) | **cuando** suena, con el timbre encima |
| `harmony` | armonia mezclada a espectro | suave (depth 0 = constante) | tonalidad ≥ 0.08 | color = espectro a brillo lleno. En pop/house denso (tonalidad 0.03-0.04) es eso **siempre** | **si** (0.000 / cota 0.030) | **que** acorde; no parpadea |
| `bars` | paleta de frase + blanqueo onset | pulso | **compas** | color = espectro: se vuelve `combo`. En summer.wav, 83.2% de frames identicos | **no** (0.336) | **estructura** 4x4 |
| `beat_flash` | fijo + blanqueo onset | pulso | reloj | naranja a `beat_floor`, sin destello | **no** (0.336) | **metronomo**; timing sin timbre |
| `spectrum` | espectro | energia | ninguno | no degrada. Sin audio cae a `idle_color` por energia ~0 | **si** (0.000) | **timbre**, sin ritmo |
| `sustain` | espectro, **sin** onset | sostenido | sustain ≥ 0.55 **y** tonalidad ≥ 0.03 | brillo = `beat_envelope` (0.336). En billie.wav mezcla 0.0%: es `combo` sin el blanqueo | **no** mientras la mezcla no este plena | destello que **se aplaca** en pads |
| `idle` | fijo | fijo | ninguno | no degrada. `sync.py` lo pone solo en silencio | **si** (0.000) | **reposo**; la app sigue viva |
| `roles` | — | — | la lista tiene que describir el area | `combo` en todos los canales | depende del look asignado | **no es un look.** Es el compositor |

`roles` no ocupa casilla. Con `channel_count=1` o lista invalida es `combo`
entero (d = 0.000, 100% de frames, medido). Con dos canales y
`("pulso","armonia")`, canal 0 **es** `combo` y canal 1 **es** `harmony`,
byte a byte.

Alias actuales, dos nombres para el mismo look:

| alias en `channel_roles` | look real |
|---|---|
| `pulso` | `combo` |
| `armonia` | `harmony` |
| `espectro` | `spectrum` |
| `sostenido` | `sustain` |

`bars`, `beat_flash`, `idle` no tienen alias. No se pueden poner en un canal
sin pasar el modo global, que pinta las **dos** luces igual via `fill()`.

---

## 3. Solapes

Misma casilla de los tres ejes = el usuario no tiene dos looks, tiene un
look y una degradacion.

### Misma casilla cuando el enganche falla

| Par | Casilla nominal | Casilla degradada | Evidencia |
|---|---|---|---|
| `bars` / `combo` | paleta+pulso vs espectro+pulso | **espectro+pulso** las dos | summer.wav: 83.2% frames d<0.02, mediana 0.000. Compas 16.8% del tema. En billie.wav el compas engancha (80.1%) y solo 19.9% se parecen: ahi NO son el mismo look |
| `sustain` / `combo` | espectro+sostenido vs espectro+pulso | **espectro+pulso**, con un matiz | billie.wav mezcla 0%: misma envolvente, `combo` blanquea onsets y `sustain` no. Mediana 0.041, 37.5% bajo 0.02. Casi la misma casilla |
| `harmony` / `spectrum` | armonia+suave vs espectro+energia | **mismo COLOR** (espectro), **distinto BRILLO** | summer.wav: `harmony_mix` = 0.0%. Media RGB 0.064, solo 22.3% indistinguibles. Mismo matiz, `harmony` a brillo lleno, `spectrum` sigue la energia |
| `roles` 1ch / `combo` | compositor vs look | **combo** | d=0.000 siempre si la lista no describe el area |

### Misma casilla de brillo, distinto color (no son el mismo look)

`combo`, `bars` y `beat_flash` comparten brillo `pulso` y el blanqueo de
onset. El color los separa (espectro / paleta / naranja fijo).
`combo` vs `beat_flash` midio **0.0%** de frames indistinguibles en todas
las condiciones: misma envolvente, distinta lampara. No fusionar por el
eje de brillo.

### Lo que no solapa

`idle` no comparte casilla con nadie cuando hay musica (0.0% vs todos).
`spectrum` no comparte brillo con `combo` (energia vs pulso; 0-2% identicos).
`harmony` vs `combo` media 0.47 en summer, 0.96 en progresion tonal.

### Choque con `docs/dos-luces.md`

Ese doc desaconsejaba un "compositor generico, un modo arbitrario por
luz" para no poner el destello en el techo. El requisito de ahora es
justamente poder combinar looks por canal. No se contradice el **riesgo**
(techo a 0.336): se resuelve etiquetando aptitud cenital, no prohibiendo
la combinacion. El par default pared=`combo` / techo=`harmony` sigue
siendo el que ese doc recomendaba.

README cita la puerta tonal de `sustain` como 0.03-0.08; `config.yaml`
tiene 0.03-0.045. No cambia la casilla: con mezcla 0, `sustain` es pulso.

---

## 4. Huecos

Rejilla color × brillo. Lo cubierto y lo que falta. Solo senales que ya
publica `AudioState` o el reloj. Nada de estado en el efecto.

|  | brillo pulso (no techo) | brillo energia (techo ok) | brillo suave/constante (techo ok) | brillo sostenido (no techo si mezcla 0) |
|---|---|---|---|---|
| color espectro | `combo` | `spectrum` | *hueco A* | `sustain` |
| color armonia | *hueco B, no conviene* | **hueco C** | `harmony` | *hueco D* |
| color paleta | `bars` | — | **hueco E** | — |
| color fijo | `beat_flash` | **hueco F** | `idle` (nivel 0.07, no es show) | *hueco G* |

Los que tienen sentido en **este** cuarto, con senal existente y look
distinto al de al lado:

### C. Armonia + energia  — el hueco util del techo

Color = `harmony_color` (con la misma rampa a espectro si no hay tono).
Brillo = max de bandas, como `spectrum`.
Enganche = tonalidad, igual que `harmony`.
Se ve: el techo pinta el acorde y **respira con la mezcla**, sin destello
a 2 Hz. Hoy `harmony` es una lampara a brillo 1.0; en pop denso se queda
en espectro lleno y no se distingue de "luz encendida". Este look
seguiria el volumen.
Puro: `chroma_hue`, `tonality`, `bands`. Nada nuevo que calcular.

### F. Fijo + energia  — wash cenital

Color = `idle_color` (o un color de config).
Brillo = energia de bandas.
Se ve: el techo no cambia de matiz (en un cuarto pequeno dos hues se
suman a sucio; `docs/dos-luces.md` lo descarto con razon) y sube/baja
con lo fuerte que suena. Distinto de `idle` (plano), de `spectrum`
(cambia de color) y de `beat_flash` (estrobo).
Puro: `idle_color`, `bands`.

### E. Paleta + suave  — 4x4 sin estrobo

Color = `phrase_palette`.
Brillo = `gentle_brightness`.
Se ve: el techo cambia de color en el "1" y no parpadea. Hoy `bars` no
puede ir al techo (0.336). Este seria `bars` cenital-seguro.
Enganche = **compas**. En summer.wav no engancha: degradaria a espectro
+ suave, o sea casi `harmony` degradado. Fragil. Util el dia que el
compas cierre; no es el primer hueco a abrir.
Puro: `bar_locked`, `phrase_phase`, paleta. El reloj ya esta.

### Los que no abriria

* **B. Armonia + pulso.** `harmony_beat_depth` ya existe y, si se sube
  sin cota, el techo estroboscopa. Con la cota 0.03 deja de ser pulso y
  se parece a `harmony`. El pulso de verdad vive en la pared (`combo`).
* **A. Espectro + constante.** Es exactamente `harmony` degradado (color
  espectro, brillo 1.0). Un nombre nuevo para lo que summer.wav ya
  muestra cuando pones `harmony`.
* **D. Armonia + sostenido.** En percusion (mezcla 0) el techo destella.
  En pads se parece a C con menos energia. No.
* **G. Fijo + sostenido.** Metronomo naranja que se aplaca en pads. Estrecho,
  y en mezcla 0 vuelve a 0.336. No para el techo.

Ninguno de los huecos buenos necesita historial en el efecto. Un desfase
pared→techo (`docs/dos-luces.md` §4.5) se evalua con `clock.phase(now - dt)`
y tambien es puro; es condimento, no un look.

---

## 5. Conjunto minimo consistente

Siete looks. Un compositor que no es look. Dos huecos de techo, despues.

### Looks que conservaria, con una responsabilidad cada uno

| Nombre | Responsabilidad | Donde |
|---|---|---|
| `combo` | cuando (pulso + timbre + onsets) | solo pared |
| `harmony` | que acorde, sin parpadeo | techo (default) |
| `spectrum` | que timbre, sin ritmo | techo |
| `bars` | estructura 4x4 | solo pared |
| `beat_flash` | metronomo / calibrar latencia | solo pared |
| `sustain` | destello que se aplaca en pads | solo pared |
| `idle` | reposo; automatico en silencio | los dos |

No fusiono `bars` con `combo`: en billie.wav se separan (19.9% identicos,
compas el 80% del tema). Se pierde el 4x4 el dia que hay "1". En house
plano el usuario tiene que saber que va a ver `combo`.

No fusiono `harmony` con `spectrum`: misma receta de color solo cuando no
hay tono. En progresion tonal la media RGB es 0.77. Se perderia el unico
look que se queda quieto en un acorde.

No fusiono `sustain` con `combo`: en summer.wav mezcla 60.1%, media 0.15.
Se perderian los pads. En billie ya degrada solo.

No fusiono `beat_flash` con `combo`: 0.0% identicos. Se perderia el
metronomo naranja, que es lo que deja ver el timing sin el espectro.

### Lo que deja de ser look

**`roles`.** Pasa a ser el mecanismo: `channel_roles` es una lista de
**nombres de look**, uno por canal. Se pierde el alias `pulso` /
`armonia` / `espectro` / `sostenido` (dos vocabularios para lo mismo).
Se gana poder poner `bars` o `idle` en un canal. Se pierde la proteccion
implicita de "solo 4 roles, y el default ya es el par bueno": hay que
sustituirla por la regla de techo, no por un subconjunto a medias.

Default de este cuarto, igual que hoy: `[combo, harmony]`.

### Huecos que anadiria, en orden, no manana

1. **wash** = fijo + energia (hueco F). Techo que respira sin pelear el
   color con la pared.
2. **harmony** con brillo de energia (hueco C), o un look aparte
   `harmony_energy`. Techo que sigue el acorde **y** la mezcla.

`paleta+suave` (hueco E) se espera a que el compas enganche en el
material real. Hoy no.

### Que se pierde si se recorta de mas

Recortar a `{combo, harmony, idle}` + compositor cubre el default del
cuarto y el silencio. Se pierde: 4x4 (`bars`), metronomo (`beat_flash`),
pads (`sustain`), timbre sin ritmo (`spectrum`). Esos cuatro no son
solapes: son looks que se apagan en un disco y se encienden en otro.
El usuario no pidio borrar; pidio responsabilidades. Con siete nombres
claros y un compositor, las tiene.

---

## 6. Recomendacion: manana

1. **Un vocabulario.** El look se llama como el modo: `combo`, `harmony`,
   `bars`, `beat_flash`, `spectrum`, `sustain`, `idle`. `channel_roles`
   acepta esos nombres. Los alias `pulso`/`armonia`/… se pueden dejar un
   tiempo como sinonimos, no como el contrato.
2. **`roles` deja de venderse como modo de color.** Es el layout. El
   modo global `combo` sigue pintando las dos luces iguales (`fill()`):
   eso es un look en los dos canales, no un fallo.
3. **Los siete looks entran en la lista de canal.** Asi `bars`,
   `beat_flash` e `idle` dejan de ser "solo a las dos luces o nada".
4. **Regla de techo, no subconjunto mudo.** Canal 1 no acepta looks de
   brillo `pulso` ni `sostenido` (0.336). Aviso en consola, igual que
   hoy cuando la lista no describe el area. Eso es lo que `dos-luces.md`
   queria evitar, sin negar la combinacion.
5. **No abrir huecos todavia.** El par `[combo, harmony]` ya es la
   combinacion consistente de este cuarto. Wash y armonia+energia
   vienen despues, cuando el techo a brillo 1.0 se quede corto.

Lo que no haria manana: tocar `fill()`, meter layout dentro de los siete
looks (el test dorado congela su RGB), ni poner `combo` en el techo
porque "queda mas alegre".
