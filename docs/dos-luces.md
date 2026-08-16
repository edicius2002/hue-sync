# Dos luces en la misma area de Entertainment

> Estado, 2026-08: analisis de diseno previo a `roles`. La configuracion vigente
> es `effects.channel_roles`, no `wall_channel` / `ceiling_channel`; las
> menciones posteriores a `dual` describen la propuesta historica. `sustain` ya
> esta cableado en `engine.py`, aunque con mezcla cero degrada a beat y no es
> seguro para una luz cenital.

Investigacion y propuesta historica. El transporte ya admite un color por
canal; `roles` es el compositor que hoy aprovecha ese grado de libertad.

## 1. Situacion

Cuarto pequeno. Dos luces en la misma entertainment area:

* una en la **pared izquierda**, respecto del setup
* otra en el **techo**, cenital

No son simetricas ni estan enfrentadas. Cualquier idea que asuma izquierda
contra derecha, o un ping-pong estereo, no encaja en esta geometria. Lo que
si encaja es un contraste **lateral contra cenital**: una luz localizada a
un lado del campo visual, y otra que ilumina el cuarto entero desde arriba.

Hoy, con dos luces, se ve exactamente lo mismo en las dos. Eso no es un
limite del bridge: es `fill()`.

## 2. Punto de partida en el codigo

### 2.1 Lo que ya esta listo

`Effect.render` devuelve `dict[int, Color]`. El backend manda un
`LightColorCommand` por cada clave, con `channel_id` igual al entero del
dict (`hue/backends.py`). `EntertainmentSession.send` no asume que todos
los canales lleven el mismo color. El loop de `sync.py` tampoco: copia
lo que el efecto devuelva.

O sea: el cable ya es por canal. El cuello esta en los efectos.

### 2.2 Lo que hace `fill()`

```python
def fill(color: Color, count: int) -> Channels:
    return {i: color for i in range(max(1, count))}
```

Los siete modos (`combo`, `harmony`, `bars`, `beat_flash`, `spectrum`,
`idle`, `sustain`) calculan **un** RGB y lo replican. `channel_count` llega
al contexto y se usa solo para saber cuantas copias hacer.

Los tests de efectos construyen el contexto con `channel_count=1` y leen
`render(...)[0]`. El test dorado (`tests/test_effects_golden.py`) congela
ese canal 0 de los seis modos originales a `abs=1e-9`. Congela el color,
no el hecho de replicarlo. Un modo nuevo que no este en
`MODOS_ORIGINALES` no entra en esa red. Cambiar `fill()` para que deje de
copiar, o retocar el RGB del canal 0 de un modo viejo, si la rompe.

### 2.3 Como se numeran los canales

CLIP v2 expone `entertainment_configuration.channels[]`. Cada entrada trae
`channel_id` (0..N-1, correlativos) y una `position` `{x, y, z}` en el
espacio del area. `BridgeClient.get_entertainment_areas` tira la posicion
y se queda solo con `channel_count = len(channels)`.

`fill()` asume ids contiguos `0 .. count-1`. Eso coincide con el contrato
habitual de HueStream, pero **el indice no es la geometria**. El canal 0
es el que se anadio primero al area, no "la pared". Sin un mapeo
explicito, cualquier rol distinto es una loteria.

La captura de audio tampoco ayuda a espacializar: el loopback se baja a
mono en `audio/capture.py`. No hay panoramico que mandar a la pared.

### 2.4 Datos de `AudioState` por frame

Disponibles hoy, publicados cada frame de analisis:

| Campo | Que es | Listo |
|---|---|---|
| `bands` (3,) | graves / medios / agudos, 0..1, pico adaptativo | si |
| `chroma_hue`, `tonality` | armonia y fiabilidad tonal | si |
| `sustain` | sostenimiento crudo 0..1 | si; detector cableado en `engine.py` |
| `last_onset_time`, `last_onset_strength` | golpes fuera de pulso | si |
| `bpm`, `locked`, `confidence` | tempo y enganche del PLL | si |
| `flux`, `rms`, `silent` | energia / silencio | si |

Fuera de `AudioState`, el render ya resuelve en `RenderContext`:

* `clock.phase(now)` / `beat_index(now)` — reloj de beat, consultable en
  cualquier instante (tambien en el pasado)
* `bar_locked`, `beat_in_bar`, `bar_phase`, `phrase_phase` — solo si
  `BarTracker` engancha

`BarTracker` engancha a `downbeat_min_confidence = 0.14`. Sobre
`summer.wav` la confianza queda en 0.046. Cualquier propuesta que dependa
del compas o de la frase es fragil en el material real con el que se
afina. El reloj de beat, en cambio, si engancha: las opciones que vivan
de `clock.phase` no heredan ese fallo.

El modo `sustain` ya existe y lee `state.sustain`, pero
`AnalysisEngine.feed` no instancia `SustainDetector` ni puebla el campo.
El default es 0.0, y el propio docstring del modo lo dice: sin cablear,
degrada a envolvente de beat. Para un rol "esta luz lleva el
sostenimiento", hoy no hay senal.

### 2.5 Coste perceptual que ya esta medido

No es teoria. El codigo ya documenta y acota esto:

* Por encima de ~0.03 de brillo por frame de render (50 fps) el ojo lee
  parpadeo. `beat_envelope` salta hasta 0.150 por frame a 120 BPM.
* `gentle_brightness` recorta la profundidad para no pasar de
  `max_step` (0.03 en harmony/sustain).
* El bridge empuja Zigbee a ~25 Hz. El render va a 50 fps. Un desfase
  entre luces menor de un paquete Zigbee (~40 ms) es invisible en la
  bombilla, da igual lo preciso que sea el calculo.
* Un corte seco en una mezcla (armonia, sustain) se midio como salto RGB
  de casi 1.0: fogonazo. Las rampas no son decorativas.

La fotosensibilidad tipica pica entre 3 y 30 Hz. Un beat a 120 BPM son
2 Hz, por debajo del pico, pero **el techo llena el campo visual**,
incluida la periferia, que es justo donde mas dispara. La pared
izquierda es un acento localizado. Regla de esta geometria: el destello
agudo va a la pared; el techo respira, no estroboscopa.

## 3. Premisa que no es un efecto: saber cual es cual

Antes de cualquier rol distinto hace falta un mapa `canal -> {pared,
techo}`. Tres caminos, de mas barato a mas automatico:

1. **Config manual.** Una tupla `channel_roles` en `EffectsConfig`, en el
   mismo orden que los canales. Riesgo nulo sobre el render. El usuario se
   equivoca una vez y lo nota.
2. **Identificar a ojo.** Un barrido que enciende los canales de uno en
   uno (hoy `huetest` manda el mismo color a todos). Cinco minutos, y el
   mapa deja de ser una apuesta. No toca efectos.
3. **Leer `position` de CLIP v2.** Techo = z mas alto, pared izquierda =
   x mas negativo. Exige enriquecer `EntertainmentArea` y no tirar el
   array de canales en `rest.py`. Depende de que las luces esten
   colocadas en el area de la app Hue; si el usuario las dejo en un
   monton, el auto-mapeo miente.

Veredicto de la premisa: hacer (1) + (2) antes que cualquier reparto por roles.
Sin eso, el resto de este documento pinta colores en el canal equivocado
y se diagnostica como "el efecto no funciona".

No hace falta tocar `fill()` para nada de lo que sigue. El sitio correcto
es un compositor (modo nuevo u opcion de layout) que, con `channel_count
< 2`, delegue al efecto actual y con 2+ asigne por rol. Los siete modos
siguen llamando a `fill()`. El dorado no se entera.

## 4. Familias

### 4.1 Espejo (lo que hace hoy)

**Idea.** Las dos luces reciben el mismo RGB. Es `fill()`.

**Datos.** Los del modo activo. No pide nada nuevo.

**Geometria.** En un cuarto pequeno el espejo no es tonto: las dos luces
mezclan en las paredes y el techo, y un solo color llena el volumen sin
pelearse. Se pierde la oportunidad de leer dos capas de la musica, pero
tampoco se ensucia. Con roles mal asignados, el espejo es mejor que un
contraste al reves (techo estroboscopico, pared apagada).

**Coste.** Cero. No se toca nada. `fill()` se queda como degradacion
segura: una luz, o dos luces sin layout configurado, o silencio (`idle`).

**Riesgos.** Los del modo elegido. El espejo no anade parpadeo: las dos
luces parpadean a la vez, que en un techo pequeno **sube** la energia
visual del destello. Eso ya pasa hoy. No depende de `BarTracker`.

**Veredicto.** Conservarlo como default. No es el objetivo, pero es el
fallback correcto y el unico que no puede pintar el canal equivocado.

### 4.2 Roles distintos: pulso contra armonia (o sostenimiento)

**Idea.** La pared lleva el *cuando* (envolvente de beat, onsets). El
techo lleva el *que* (color armonico, o brillo continuo si hay
sostenido). No es un invento: los modos `combo` y `harmony` ya estan
escritos como mitades de esa separacion. `harmony_beat_depth` vale 0.0
aposta, y el docstring lo dice: `combo` lleva el ritmo, `harmony` la
armonia.

**Datos.**

* Pulso: `BeatClock` + `beat_envelope` + `onset_accent`. Ya existen.
* Armonia: `chroma_hue`, `tonality`, `harmony_mix`. Ya existen. Sin
  tonalidad suficiente el techo cae a `spectrum_color`, igual que el
  modo `harmony` a solas. Degradacion segura.
* Sostenimiento: `state.sustain` y `SustainDetector` estan cableados. Con
  mezcla cero degrada a `beat_envelope`, asi que techo=`sostenido` sigue
  estroboscopando en material percusivo y no es una opcion segura por defecto.

**Geometria.** Esta es la que mejor encaja. La pared izquierda pega el
golpe donde se mira el setup. El techo tiñe el cuarto con el acorde y
casi no baja de brillo, asi que el volumen no se apaga entre beats. En
un cuarto pequeno el color del techo es el ambiente; el destello de la
pared es el acento. Si se invierten los roles, el techo estroboscopa y
la pared se queda en un color quieto que apenas se lee: peor.

**Coste.** Bajo, si se hace como compositor y no reescribiendo modos.

* Nuevo modo (p. ej. `dual`) o flag de layout en `EffectsConfig`.
* `effects/modes.py`: una clase que llama a `ComboEffect.render` y
  `HarmonyEffect.render`, toma el canal 0 de cada uno, y escribe
  `{pared: ..., techo: ...}`. Cero matematica nueva.
* `config.py`: ids de canal. Opcional: `cli/sync.py` para imprimir los
  dos RGB (hoy `_status` enseña `next(iter(channels.values()))`, o sea
  solo el canal 0).
* No se toca `fill()`. No se tocan los siete modos. El dorado sigue
  verde. Tests nuevos del compositor, con `channel_count=2`.

**Riesgos.**

* Parpadeo: el de `combo` en la pared, que ya se acepta. El techo, con
  `harmony` por defecto, es plano. Bien.
* Epilepsia: mejor que el espejo de `combo`, porque el techo deja de
  destellar. No poner `beat_envelope` en el techo.
* Sucio: poco, si el techo no pulsa. El riesgo real es pintar la armonia
  en la pared y el pulso en el techo por un mapa al reves.
* `BarTracker`: no. `harmony` no lo usa. `combo` solo acentua el "1"
  cuando hay enganche; sin el, todos los beats pesan igual, que es el
  degradado ya disenado.
* Sustain como segundo rol: no hasta cablear el detector. Eso seria
  `engine.py` + tests de integracion, fuera de este alcance visual, y
  ademas el modo `sustain` ya tiene umbrales provisionales.

**Veredicto.** **Si, y es lo primero que vale la pena implementar.** Reusa
modos que ya estan calibrados, encaja en la geometria, no depende del
compas, no rompe `fill()` ni el dorado. La variante sustain se deja para
cuando la senal exista de verdad.

### 4.3 Split por frecuencia: graves en una, medios/agudos en la otra

**Idea.** Una luz pinta con `bands[0]`, la otra con `bands[1]` y
`bands[2]`. Color por banda (`bass_color` / `mid_color` / `treble_color`)
y brillo por el nivel de esa banda.

**Datos.** `state.bands` ya esta, normalizado por `BandLevels` (pico
adaptativo, ataque 5 ms, release 150 ms). No hace falta calcular nada
nuevo. `spectrum_color` mezcla las tres; aqui habria que *no* mezclarlas,
o mezclar solo un subconjunto. Primitiva nueva pequena en `base.py`
(por ejemplo color de una banda, o de un par), sin cambiar
`spectrum_color`: el dorado de `combo`/`spectrum`/`bars` la usa.

**Geometria.** Un split duro graves/agudos en este cuarto se lee mal.
Los graves no "viven a la izquierda" ni los agudos "en el techo": las
dos luces iluminan el mismo volumen pequeno y los colores **se suman en
el aire y en las paredes**. Rojo de graves mas azul de agudos da un
marron sucio, justo lo que `saturate` intenta evitar en una sola luz.
Un mapeo "graves al techo, agudos a la pared" tiene una historia
(el bombo llena el cuarto, el hi-hat chispea al lado), pero el cuarto
pequeno la borra.

Un split **blando** (las dos luces comparten tono, el techo pondera
graves en el brillo, la pared pondera agudos) ensucia menos. Sigue
siendo un `spectrum` con dos pesos, no un equalizer visual.

**Coste.** Medio-bajo. Primitiva en `base.py` + modo/compositor nuevo.
`spectrum_color` no se toca. `fill()` no se toca. El dorado no se entera
si los modos viejos siguen llamando a la mezcla de siempre.

**Riesgos.**

* Parpadeo: la banda de graves es picuda (bombo). Mandarla al techo con
  brillo lineal reproduce el problema de `beat_envelope` en el sitio
  peor. Haria falta `gentle_brightness` o un suelo alto en el techo.
* Sucio: el riesgo principal, por mezcla aditiva en cuarto pequeno.
* `BarTracker`: no.
* En pasajes de un solo timbre (pad, voz sola) una de las dos luces se
  apaga. Eso se lee como "se ha colgado", no como "no hay agudos".

**Veredicto.** **No como split duro.** Como ponderacion blanda de brillo
sobre el mismo color, puede ser un parametro del compositor de 4.2, no
una familia aparte. No justifica un modo propio ahora.

### 4.4 Split temporal: alternancia por beat o por compas

**Idea.** Un beat (o un compas) manda una luz, el siguiente la otra. La
que no toca se queda en suelo o apagada.

**Datos.**

* Por beat: `clock.beat_index(now) % 2`. Existe en cuanto el PLL
  engancha. **No necesita `BarTracker`.** Sin lock, no hay indice: hay
  que degradar a espejo, no a un flip-flop aleatorio.
* Por compas: `beat_in_bar` / `bar_phase`. Existe solo con
  `bar_locked`. Sobre `summer.wav` no engancha. Fragil.

**Geometria.** No es un ping-pong izquierda-derecha, es un interruptor
pared/techo. En un cuarto pequeno se lee como "el cuarto cambia de
fuente de luz cada golpe": dramatico un rato, cansado en un tema. El
techo apagandose cada dos beats es un parpadeo de habitacion, no un
acento. Si la alternancia es por compas y el detector esta en el "3"
(`BarTracker.ambiguous`), el cambio cae medio compas corrido: se nota,
y encima solo cuando hay enganche, o sea a ratos.

**Coste.** Bajo en codigo (un indice modulo 2 y dos colores). Alto en
calibracion perceptual. Tocar `fill()` no hace falta. El acento de
downbeat de `beat_envelope` ya usa `bar_locked`; reutilizar esa rama
para apagar una luz mezclaria dos features y ensuciaria el dorado si se
metiera dentro de la primitiva.

**Riesgos.**

* Parpadeo y epilepsia: los mas altos de toda la lista. Alternar fuentes
  que llenan el campo visual, con contraste fuerte, es el patron que hay
  que evitar. Aunque 2 Hz este por debajo del pico fotosensible, el
  techo que se apaga es un estimulo grande. `beat_floor` mitiga; apagar
  del todo, no.
* Sucio: en el cambio de luz, si no hay cruce, hay un escalon. Un cruce
  suave (las dos encendidas, una baja y la otra sube) deja de ser
  "alternancia" y se parece a 4.5.
* Compas: la variante por compas se descarta. La de beat sobrevive solo
  con suelo alto y sin apagar el techo.

**Veredicto.** **Descartar la alternancia por compas.** La de beat, como
efecto principal, no: es vistosa y fragil a la vez, y pelea con la
geometria. Si algun dia se quiere un modo "show", que sea opt-in y con
el techo nunca por debajo de un suelo alto.

### 4.5 Desfase: la misma envolvente, retardada

**Idea.** Las dos luces hacen lo mismo, pero una va detras. En esta
geometria el unico desfase que cuenta es **pared primero, techo despues**:
el golpe nace al lado y sube a llenar el cuarto. Un desfase al reves
(techo primero) se lee como eco que cae, no como kick que abre.

**Datos.** Para la envolvente de beat, **ya estan**, y el calculo sigue
siendo puro. `BeatClock.phase` se puede preguntar en `now - dt` porque
es un oscilador, no un historial. No hace falta un ring buffer ni estado
en el efecto. Se evalua `beat_envelope` sobre un contexto con `now`
retrasado, o se extrae la fase a mano.

Para bandas, onsets y chroma el pasado **no se puede reconstruir**. Un
onset ya llega tarde (por eso usa `now_real` y no el lookahead).
Retrasarlo mas lo enseña apagado. Retrasar el color espectral exigiria
guardar N frames de `AudioState`, romper la regla de "el efecto no
guarda nada", o contaminar el publisher. No vale la pena para un eco.

**Geometria.** Un dt corto (80-200 ms) es un bloom vertical: la pared
pega y el techo contesta. Encaja. Un dt de un beat entero (~500 ms a
120 BPM) se lee como que una luz va mal de sync. Por debajo de ~40 ms el
Zigbee lo borra.

**Coste.** Bajo para el eco de beat: compositor que llama dos veces a la
misma primitiva con dos `now`. `fill()` intacto. Dorado intacto. No
toca analisis.

**Riesgos.**

* Parpadeo: dos destellos de `beat_envelope` desfasados **doblan** la
  tasa aparente de flashes en el cuarto (pared en t, techo en t+dt). A
  120 BPM con dt = 150 ms se parecen a un patrón irregular, no a un
  pulso. El techo, otra vez, no deberia llevar el pico agudo.
* Epilepsia: peor que el espejo si las dos pican. Mejor si el techo usa
  `gentle_brightness` retrasada y la pared el pico.
* Sucio: un dt mal elegido parece latencia, que es justo lo que el
  proyecto paso trabajo en compensar (`latency_compensation_ms`). El
  usuario va a calibrar a ojo y a odiarlo si "una luz llega tarde".
* `BarTracker`: no.

**Veredicto.** **Si, pero como condimento del compositor de 4.2, no como
modo.** Pared con `beat_envelope` al `now` compensado; techo con
`gentle_brightness` a `now - 100..150 ms`, mismo color armonico. El
desfase de color espectral o de onsets, no.

### 4.6 Contraste de saturacion o de brillo (base + acento)

**Idea.** Las dos luces comparten tono. El techo es la base: mas apagado
o menos saturado, casi constante. La pared es el acento: mas saturada y
con la envolvente de beat. No hay dos colores peleando en el cuarto.

**Datos.** Los mismos que 4.2. `saturate` y `scale` ya existen.
`harmony_color` ya baja saturacion cuando `tonality` es baja. No hay que
calcular nada aguas arriba. Un par de factores en config
(`ceiling_brightness`, `wall_saturation_boost`) bastan.

**Geometria.** La mejor version "misma familia de color" para un cuarto
pequeno. El techo tiñe sin gritar; la pared marca el pulso sin inventar
un segundo matiz que se mezcle a sucio. Es, de hecho, lo que el ojo va a
leer aunque se implemente 4.2 con `harmony` plano en el techo y `combo`
en la pared: `combo` ya satura y escala por beat, `harmony` ya va a
brillo 1.0. Esta familia no es una alternativa a 4.2, es su calibracion.

Si se hace sobre un solo modo (las dos con `spectrum_color`, techo al
0.4, pared con envolvente) tambien funciona, y sobrevive cuando no hay
armonia. Util como degradado.

**Coste.** Muy bajo una vez existe el compositor. No toca `fill()`. No
toca primitivas de color si se `scale`/`saturate` a la salida. Dorado
intacto.

**Riesgos.**

* Parpadeo: el del acento, localizado. El techo quieto. Bien.
* Sucio: el mas bajo de las familias con roles distintos, porque no hay
  dos hues.
* Si el contraste de brillo es extremo, la pared "parpadea sola" y el
  techo parece una lampara de mesa que no esta en el show. Hay que dejar
  que el techo respire un poco (`harmony_beat_depth` pequeno, ya acotado
  por `harmony_max_step`).
* `BarTracker`: no.

**Veredicto.** **Si, como parametros del primer compositor, no como modo
aparte.** Es lo que hace que 4.2 se vea limpio en un cuarto pequeno en
vez de "dos shows distintos".

### 4.7 Combinar dos modos distintos, uno por luz

**Idea.** No partir un modo, sino correr dos. Pared = `combo` (o
`beat_flash`). Techo = `harmony` (o `spectrum`, o `sustain`).

Esto solapa con 4.2 a proposito: 4.2 es el caso particular que vale la
pena. Aqui se evalua el mecanismo general y los emparejamientos malos.

**Datos.** Los de cada modo. Todos estan en `AudioState` /
`RenderContext`, salvo `sustain` cableado. Un compositor generico
(`layout: combo,harmony`) no pide analisis nuevo.

**Geometria.** Solo son utiles los pares **ortogonales**: una luz dice
cuando, la otra dice que.

| Pared | Techo | Encaja | Por que |
|---|---|---|---|
| `combo` | `harmony` | si | pulso local + acorde ambiente. El par natural |
| `beat_flash` | `harmony` | si, peor | igual pero el acento es color fijo, menos musical |
| `combo` | `spectrum` | si, degradado | cuando no hay tonalidad; `harmony` ya cae aqui sola |
| `combo` | `sustain` | si, luego | techo continuo en pads; hoy la senal es 0 |
| `combo` | `bars` | no | `bars` necesita `BarTracker`; ademas rota paleta en el techo, que es donde el color tiene que estar quieto |
| `bars` | `harmony` | no | las dos quieren ser "el color"; ninguna pega el pulso |
| `combo` | `beat_flash` | no | las dos pulsan, color distinto. Sucio y redundante |
| `combo` | `combo` | eso es el espejo, o 4.5 si hay dt | no es "dos modos" |
| `spectrum` | `spectrum` | no | sin pulso, dos equalizers. Ver 4.3 |
| `idle` | cualquiera | no | el idle es el silencio, y `sync.py` ya sustituye el efecto entero cuando `state.silent` |

**Coste.** El compositor generico es poco mas que el de 4.2 mas dos
nombres en config. La tentacion es hacerlo demasiado flexible
(`HUEBPM_EFFECTS_WALL_MODE`, etc.) antes de haber visto una sola
combinacion en las luces. Cada par hay que calibrarlo: `combo` en la
pared ya blanquea onsets (`apply_onset_flash`); si el techo tambien
reacciona a algo rapido, el cuarto parpadea en dos sitios.

No se toca `fill()`. No se reescriben los siete modos: se instancian y se
les pide `render`, se toma `[0]`. El dorado no corre el compositor.
Cuidado con `test_todos_los_modos_devuelven_rgb_valido`, que recorre
`EFFECTS`: un modo nuevo tiene que devolver RGB en rango tambien con
`channel_count=1` (ahí, espejo o delegacion al primero).

**Riesgos.**

* Un compositor generico invita a pares malos. Mejor un modo `dual` con
  un par fijo, y mas adelante un segundo par, que una matriz.
* `bars` y cualquier cosa con `bar_locked` heredan la fragilidad de
  `summer.wav`.
* `sync.py` en silencio usa `IdleEffect` para **todas** las luces. Eso
  esta bien: las dos deben ir a reposo juntas. El compositor no debe
  pelearse con esa rama.
* Epilepsia: depende del par. `combo`+`harmony` alivia. `combo`+`combo`
  desfasado empeora.

**Veredicto.** **Si el mecanismo, no la matriz.** Implementar un par
fijo (`combo` pared, `harmony` techo). No abrir "un modo por luz" en la
CLI hasta haberlo visto en el cuarto. Descartar cualquier par que meta
`bars` o dos pulsos.

## 5. Familias extra

### 5.1 Chase vertical (envolvente que sube)

No es ping-pong. Es 4.5 restringido a la geometria: brillo de pared =
`beat_envelope(now)`, brillo de techo = `gentle_brightness(now - dt)` o
incluso una rampa que **cruza** de una a otra a lo largo del beat
(pared maxima en fase 0, techo maxima en fase 0.25). Datos: solo el
reloj. Coste bajo. Riesgo de parpadeo si el cruce es un escalon; con
coseno, no. **Vale la pena como segundo paso**, encima de 4.2, si el par
estatico se queda corto.

### 5.2 Onsets a la pared, pulso al techo

Los onsets ya se disenan como blanqueo de color porque, con una sola
luz, el brillo extra se satura cerca del beat (`apply_onset_flash`). Con
dos luces se podria dejar el techo en armonia continua y **reservar la
pared para el golpe fuera de tiempo**. El problema: en musica a pulso
claro la pared se quedaria casi apagada, y el "cuando" desapareceria
del campo visual del setup. Mejor dejar los onsets como estan: acento
encima del pulso de la pared, no en vez del pulso. **No como modo.**

### 5.3 Estereo / ping-pong L-R

La captura es mono. La geometria no es L-R. **Descartado** aunque
alguien recupere el estereo del loopback.

### 5.4 Colores complementarios (`hue` y `hue+0.5`)

Vistoso en un render 3D. En un cuarto pequeno los complementarios se
suman hacia el gris. Pelea con `saturate` y con el trabajo de armonia.
**Descartado.**

### 5.5 Swap de roles cada frase

Depende de `phrase_phase` y de `BarTracker`. Sobre `summer.wav` no
engancha. Aunque enganchara, cambiar "quien es el pulso" a mitad de tema
recalibra el ojo a la fuerza. **Descartado.**

### 5.6 Degradado por posicion 3D

Con N luces, interpolar color entre roles segun `{x,y,z}`. Con dos luces
es exactamente el mapa pared/techo. No aporta hasta que haya una tercera.
No hace falta disenarlo ahora; si se leen posiciones para el mapeo
automatico, el dato queda ahi.

## 6. Que no hay que hacer, en codigo

* **No cambiar `fill()`.** Es la primitiva de "un color, todos los
  canales". Siete modos y al menos un test (`test_fill_replica_en_todos_los_canales`)
  dependen de eso. El layout vive encima.
* **No hacer los siete modos conscientes del layout.** El dorado congela
  su RGB. Un `if channel_count >= 2` dentro de `ComboEffect` es la forma
  mas cara de romper esa red el dia que el if roce el canal 0.
* **No meter `BarTracker` en el camino critico del dual.** El acento de
  downbeat ya es opt-in via `bar_locked`; el dual no deberia exigirlo.
* **No apagar el techo.** Suelo alto, o `gentle_brightness`. El techo es
  el campo visual.
* **No adivinar que el canal 0 es la pared.**

## 7. Recomendacion

Orden de trabajo, concreto:

1. **Mapa de canales.** `channel_roles` en orden de canal, tras usar
   `identify` para no adivinar. Sin esto no se calibra nada a ojo.
2. **Compositor `roles`.** Asigna `pulso`, `armonia`, `espectro` o
   `sostenido` por canal y degrada a `combo` si la lista no describe el area.
3. **Desfase corto pared → techo (100-150 ms) como opcion apagada por
   defecto.** El techo usa `gentle_brightness` retrasada, no
   `beat_envelope`. Se enciende si el par estatico se queda corto. Esto
   es 4.5 / 5.1, no un modo nuevo.
4. **Calibrar `sostenido` en pads.** El detector ya esta cableado, pero en
   material percusivo su mezcla cae a cero y el efecto vuelve a destellar;
   no asignarlo al techo sin una medicion especifica.

Descartar, y no dejarlo "para mas adelante" como si fuera deuda:

* ping-pong L-R y estereo (geometria y captura)
* alternancia por compas y swap por frase (`BarTracker` a 0.046)
* alternancia por beat como modo principal (techo estroboscopico)
* split duro graves/agudos (mezcla sucia en cuarto pequeno)
* colores complementarios
* compositor generico "un modo arbitrario por luz"
* tocar `fill()` o los siete modos para colar el layout

Lo vistoso y fragil, dicho claro: un techo que se apaga a contratiempo
se ve "de discoteca" en un video y se odia en un cuarto pequeno a los
dos minutos. Un eco de un beat entero se ve como una luz desincronizada.
Un equalizer visual rojo/azul se ve sucio en las paredes. El par
`combo`+`harmony` es menos espectacular en el primer GIF y es el unico
que esta alineado con los modos que el proyecto ya afino, con los datos
que ya salen cada frame, y con una pared a la izquierda y un techo
arriba.
