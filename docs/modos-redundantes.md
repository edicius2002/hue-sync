# Modos redundantes: misma luz, distinto nombre

Pregunta: sobre musica real, hay modos que producen la **misma luz**.
No "se parecen en el codigo". El usuario decide despues; aqui no se borra nada.

Distancia: euclidea en RGB, `sqrt((r1-r2)^2+(g1-g2)^2+(b1-b2)^2)`. Rango 0..1.732.
Umbral de "indistinguible en una bombilla": **d < 0.02**, el que pide el encargo.
Render a 50 fps con 120 ms de lookahead, mismo `RenderContext` que `sync.py`.
Se excluyen frames en silencio (`state.silent`): en vivo `sync.py` sustituye
cualquier modo por `idle` ahi, y comparar contra eso seria tautologico.
`idle` se compara como modo elegido a mano, con musica sonando.

WAV: `D:\Work\research\hue\summer.wav` y `billie.wav` (25 s, gitignorados).
Sintetico: `click_track`, `progression`, `sustained_pad` de `testing/synth.py`.

`roles` se midio dos veces: a 1 canal (degrada a `combo` si la lista no
describe el area; el default es dos roles) y a 2 canales con
`channel_roles=("pulso","armonia")`, que es el caso real del cuarto.

---

## 0. Que senal habia, de verdad

Sin esto las distancias mienten. Un par "identico" puede serlo porque el
enganche que los separa no existio en ese WAV.

| Condicion | s | BPM | clock lock | bar lock | bar conf | tonalidad | harmony_mix>0 | sustain_mix>0 | frames |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| summer.wav | 25 | 128.0 | 88.0% | **16.8%** | **0.046** | 0.041 | **0.0%** | **60.1%** | 1249 |
| billie.wav | 25 | 116.8 | 87.9% | **80.1%** | 0.133 (queda enganchado) | 0.035 | 2.6% | **0.0%** | 1249 |
| synth_compas (bateria 4/4, downbeat x2.5) | 20 | 119.9 | 84.8% | **74.8%** | **0.436** | 0.049 | 7.1% | 0.0% | 310* |
| synth_tonal (I-vi-IV-V, sin bateria) | 16 | 92.9** | 81.2% | 19.0% | 0.125 | **0.336** | **98.9%** | 79.1% | 799 |
| synth_pad (acorde largo) | 12 | 170.4** | 75.0% | 8.8% | 0.051 | **0.344** | **98.5%** | 72.8% | 599 |
| synth_favorable (pad+bateria) | 16 | 119.9 | 81.2% | 31.3% | 0.106 | 0.244 | **98.9%** | 78.8% | 799 |

\* El click track pasa el 69% del tiempo bajo el umbral de silencio (huecos
entre golpes). Los 310 frames son los que suenan.
\*\* Tempo fantasma: no hay pulso real. `combo` destella igual. Importa para
`sustain`, que es el que apaga ese destello falso.

Lectura rapida: summer no tiene compas ni armonia; si tiene sostenido.
Billie tiene compas y cero sostenido. El sintetico tonal y el pad tienen
armonia de verdad. Solo `synth_compas` engancha el compas con holgura.

---

## 1. Matrices

Por cada condicion: porcentaje de frames con d < 0.02 (arriba a la derecha)
y distancia media (abajo a la izquierda). La diagonal es 100 / 0.

`roles` en estas matrices es **1 canal**. A 1 canal es `combo` con otro
nombre; el caso de 2 luces va en la seccion 1.7.

### 1.1 summer.wav — el material house/pop del usuario

Triangulo superior: % de frames con d < 0.02. Triangulo inferior: distancia media.

|  | combo | harmony | bars | beat_flash | spectrum | sustain | idle | roles |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| combo | — | 0.2 | **83.2** | 0.0 | 0.8 | 21.2 | 0.0 | **100.0** |
| harmony | 0.468 | — | 0.2 | 0.0 | 22.3 | 2.8 | 0.0 | 0.2 |
| bars | **0.036** | 0.477 | — | 0.0 | 0.8 | 17.5 | 0.0 | **83.2** |
| beat_flash | 0.211 | 0.506 | 0.221 | — | 0.0 | 0.0 | 0.0 | 0.0 |
| spectrum | 0.413 | 0.064 | 0.424 | 0.463 | — | 4.5 | 0.0 | 0.8 |
| sustain | 0.146 | 0.420 | 0.170 | 0.282 | 0.365 | — | 0.0 | 21.2 |
| idle | 0.292 | 0.742 | 0.308 | 0.392 | 0.678 | 0.327 | — | 0.0 |
| roles | **0.000** | 0.468 | 0.036 | 0.211 | 0.413 | 0.146 | 0.292 | — |

Mediana `combo|bars` = **0.000**. Maxima 0.651 (los pocos segundos en que el
compas engancho y se solto). `harmony|spectrum` media 0.064, mediana 0.049:
mismo color, brillo distinto.

### 1.2 billie.wav — el material percusivo del usuario

Misma convencion: % arriba-derecha, media abajo-izquierda.

|  | combo | harmony | bars | beat_flash | spectrum | sustain | idle | roles |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| combo | — | 0.2 | **19.9** | 0.0 | 1.8 | 37.5 | 0.0 | **100.0** |
| harmony | 0.519 | — | 0.1 | 0.0 | 3.2 | 0.3 | 0.0 | 0.2 |
| bars | **0.183** | 0.585 | — | 0.0 | 0.2 | 3.7 | 0.0 | 19.9 |
| beat_flash | 0.182 | 0.519 | 0.211 | — | 0.0 | 0.0 | 0.0 | 0.0 |
| spectrum | 0.274 | 0.326 | 0.363 | 0.335 | — | 2.6 | 0.0 | 1.8 |
| sustain | 0.071 | 0.586 | 0.220 | 0.226 | 0.311 | — | 0.6 | 37.5 |
| idle | 0.240 | 0.752 | 0.305 | 0.326 | 0.426 | 0.173 | — | 0.0 |
| roles | **0.000** | 0.519 | 0.183 | 0.182 | 0.274 | 0.071 | 0.240 | — |

Aqui `bars` **no** es `combo`: mediana 0.156, 80% del tema con compas
enganchado. `sustain` tampoco es identico (mezcla 0.0% del tiempo, pero
`combo` blanquea onsets y `sustain` no: mediana 0.041, maxima 0.690).

### 1.3 synth_compas — bateria 4/4 con "1" marcado

El caso que summer no da: compas de verdad (confianza 0.436).

| par | media | mediana | max | % < 0.02 |
|---|---:|---:|---:|---:|
| combo \| bars | 0.143 | 0.147 | 0.411 | **25.2** |
| combo \| sustain | 0.121 | 0.049 | 0.704 | 15.5 |
| combo \| roles | 0.000 | 0.000 | 0.000 | **100.0** |
| harmony \| spectrum | 0.331 | 0.257 | 0.746 | 0.0 |
| combo \| beat_flash | 0.183 | 0.169 | 0.413 | 0.0 |
| combo \| harmony | 0.535 | 0.549 | 0.888 | 0.0 |
| combo \| spectrum | 0.297 | 0.296 | 0.622 | 0.6 |
| combo \| idle | 0.265 | 0.243 | 0.753 | 0.0 |

`bars` se separa de `combo` en cuanto hay metrica. El 25.2% identico es el
arranque antes de enganchar, no el regimen.

### 1.4 synth_tonal — progresion de acordes, sin bateria

Armonia de verdad (tonalidad 0.336, `harmony_mix` activa el 98.9%).

| par | media | mediana | max | % < 0.02 |
|---|---:|---:|---:|---:|
| combo \| bars | 0.035 | 0.000 | 0.714 | **81.0** |
| combo \| sustain | 0.298 | 0.317 | 0.761 | 9.6 |
| combo \| roles | 0.000 | 0.000 | 0.000 | **100.0** |
| harmony \| spectrum | **0.769** | 0.732 | 1.172 | **0.4** |
| combo \| harmony | **0.957** | 0.965 | 1.322 | 0.0 |
| combo \| beat_flash | 0.151 | 0.112 | 0.508 | 0.0 |
| combo \| spectrum | 0.496 | 0.564 | 0.714 | 0.9 |

Este es el numero que mata la fusion `harmony`+`spectrum`: media 0.77, casi
nunca bajo el umbral. En summer se parecen porque **no hay armonia que
seguir**. En una progresion clara son dos luces distintas.

### 1.5 synth_pad — acorde sostenido

| par | media | mediana | max | % < 0.02 |
|---|---:|---:|---:|---:|
| combo \| bars | 0.017 | 0.000 | 0.406 | **91.2** |
| combo \| sustain | **0.266** | 0.274 | 0.750 | **6.7** |
| combo \| roles | 0.000 | 0.000 | 0.000 | **100.0** |
| harmony \| spectrum | 0.785 | 0.799 | 0.905 | 1.3 |
| combo \| harmony | 0.861 | 0.867 | 1.049 | 0.0 |

El reloj se inventa 170 BPM sobre un pad. `combo` destella a un pulso que
no existe. `sustain` (mezcla activa 72.8%) es el unico que deja de
parpadear. Fusionar `sustain` con `combo` perderia exactamente este caso.

### 1.6 synth_favorable — pad + bateria a 120

Las tres senales a la vez. El compas no se queda enganchado (0.106 < 0.14).

| par | media | mediana | max | % < 0.02 |
|---|---:|---:|---:|---:|
| combo \| bars | 0.068 | 0.000 | 0.829 | 68.7 |
| combo \| sustain | 0.248 | 0.245 | 0.709 | **2.0** |
| combo \| roles | 0.000 | 0.000 | 0.000 | **100.0** |
| harmony \| spectrum | 0.883 | 0.917 | 1.153 | 0.6 |
| combo \| harmony | 0.969 | 0.960 | 1.324 | 0.0 |
| combo \| beat_flash | 0.167 | 0.131 | 0.483 | 0.0 |
| combo \| spectrum | 0.428 | 0.455 | 0.702 | 0.0 |

Con pad y pulso a la vez, `sustain` y `harmony` no se parecen a nadie.
`bars` sigue a medias, porque el compas no cerro.

### 1.7 `roles` a 2 canales (`pulso`, `armonia`)

| par | summer %<0.02 (media) | billie | synth_compas | synth_tonal | synth_pad | synth_favorable |
|---|---|---|---|---|---|---|
| pulso vs combo | **100.0 (0.000)** | **100.0 (0.000)** | **100.0 (0.000)** | **100.0 (0.000)** | **100.0 (0.000)** | **100.0 (0.000)** |
| armonia vs harmony | **100.0 (0.000)** | **100.0 (0.000)** | **100.0 (0.000)** | **100.0 (0.000)** | **100.0 (0.000)** | **100.0 (0.000)** |
| pulso vs armonia | 0.2 (0.468) | 0.2 (0.519) | 0.0 (0.535) | 0.0 (0.957) | 0.0 (0.861) | 0.0 (0.969) |
| armonia vs spectrum | 22.3 (0.064) | 3.2 (0.326) | 0.0 (0.331) | 0.4 (0.769) | 1.3 (0.785) | 0.6 (0.883) |

A 2 luces, `roles` no inventa un noveno look: el canal `pulso` **es**
`combo` y el canal `armonia` **es** `harmony`, byte a byte. Lo que anade
es repartirlos. A 1 luz, `roles` **es** `combo` (100% d=0.000 en las seis
condiciones).

---

## 2. Veredicto por par

### IDENTICOS SIEMPRE

**`roles` (1 canal) = `combo`.** Distancia 0.000 en el 100% de los frames
de las seis condiciones. No es una coincidencia de material: la lista
default tiene dos roles y un solo canal no la valida, asi que `render`
devuelve `combo` entero. Candidato a no contarse como look aparte. Con
dos luces bien configuradas deja de serlo (ver abajo).

**`roles` a 2 canales, canal a canal:** `pulso` = `combo` y `armonia` =
`harmony`, tambien d=0.000 siempre. `roles` es un compositor, no un
efecto nuevo.

Ningun otro par dio d=0 en toda condicion.

### IDENTICOS EN LA PRACTICA

**`bars` vs `combo` sobre summer.wav.** 83.2% de frames bajo 0.02,
mediana 0.000, media 0.036. El compas solo estuvo enganchado el 16.8%
del tema (confianza final 0.046 < 0.14). Sobre **ese** WAV, `bars` es
`combo` con otro nombre.

No son identicos siempre: en billie.wav el compas se queda enganchado
(80.1% de frames, histeresis: confianza 0.133, umbral de entrada 0.14,
de salida 0.07) y solo el 19.9% de los frames se parecen. En
`synth_compas` (confianza 0.436) baja a 25.2% identicos, media 0.143.
La decision no es tecnica: si el usuario escucha sobre todo house
four-on-the-floor, `bars` no le da nada. Si escucha material con "1"
detectable, es el unico que pinta el 4x4.

**`sustain` vs `combo` sobre billie.wav.** Mezcla de sustain a 0.0% del
tiempo, como esta calibrado. No son el mismo RGB: mediana 0.041, 37.5%
bajo el umbral, maxima 0.690. La diferencia es el blanqueo de onsets,
que `combo` hace y `sustain` no. En un tema seco se ven casi iguales
salvo en los golpes fuera de tiempo. En summer.wav (mezcla activa 60.1%)
ya no: 21.2% identicos, media 0.146. En un pad, 6.7% identicos, media
0.266.

**`harmony` vs `spectrum` sobre summer.wav, a medias.** `harmony_mix` =
0.0% del tiempo, o sea el color **es** `spectrum_color`. Pero `harmony`
va a brillo lleno y `spectrum` escala por energia. Resultado: media
0.064, mediana 0.049, solo 22.3% bajo 0.02. Mismo matiz, distinta
lampara. En billie se alejan (media 0.326, energia mas picuda). En
progresion tonal no se parecen nada (media 0.77, 0.4% identicos).

### REALMENTE DISTINTOS

Numeros que lo demuestran, el mas chico de las seis condiciones:

| par | peor % < 0.02 | peor media | por que se ven distintos |
|---|---:|---:|---|
| combo \| harmony | 0.0 (synth) / 0.2 (WAV) | 0.468 (summer) | pulso+timbre vs acorde a brillo fijo |
| combo \| beat_flash | **0.0 siempre** | 0.151 | misma envolvente, color naranja fijo vs espectro |
| combo \| spectrum | 0.0-1.8 | 0.274 | beat vs energia, sin pulso |
| combo \| idle | **0.0 siempre** | 0.235 | destello vs naranja tenue fijo |
| harmony \| idle | **0.0 siempre** | 0.742 | brillo lleno vs 0.07 |
| beat_flash \| idle | **0.0 siempre** | 0.326 | el metronomo vs el reposo; mismo color base, distinto nivel |
| beat_flash \| spectrum | **0.0 siempre** | 0.335 | naranja ritmico vs espectro sin ritmo |
| pulso vs armonia (roles 2ch) | 0.0-0.2 | 0.468 | las dos luces del area no se copian |

`idle` con musica sonando nunca se confunde con otro modo. En silencio
`sync.py` lo pone solo, y ahi comparar no tiene sentido.

---

## 3. Propuesta de consolidacion

Sobre **summer.wav**, los ocho nombres se reducen a **cinco luces**
distinguibles:

1. `combo` = `bars` = `roles` a 1 canal
2. `sustain` (el pad del tema, 60% del tiempo)
3. `beat_flash` (metronomo naranja)
4. `spectrum` (energia, sin beat)
5. `harmony` (espectro a brillo lleno; cerca de 4, no de 1)
6. `idle` si lo elegis a mano

Sobre **billie.wav**, `bars` se despega y `sustain` se pega. El recuento
depende del disco, no del codigo.

### Conservaria (como look de usuario)

* **`combo`.** El default. No se toca.
* **`harmony`.** En el material del usuario casi no hay acordes, y aun
  asi no es `spectrum` (brillo). En una progresion es el look mas lejos
  de `combo` (media 0.96). Fusionarlo con `spectrum` perderia el unico
  modo que se queda quieto en un acorde. El usuario no lo va a ver en
  summer; lo va a ver el dia que ponga piano o pads tonales.
* **`spectrum`.** El unico sin ritmo. 0-2% de overlap con `combo` en
  todo lo medido.
* **`sustain`.** En summer es el que mas se nota despues de `combo`
  (media 0.15, 21% identicos). En un pad es el que evita el destello
  fantasma. Fusionarlo con `combo` perderia summer y los pads, y solo
  "ahorraria" billie, donde ya degrada solo.
* **`idle`.** No es un show. Es el reposo. Ademas `sync.py` lo usa
  como automatico. No se fusiona con nada.
* **`roles`.** No como noveno look: como **layout**. A 1 luz es
  `combo`. A 2 luces es `combo` en una y `harmony` en la otra, que en
  este cuarto (pared + techo) es el contraste que el espejo no da.
  El nombre describe el area, no un color. Conservarlo. No anunciarlo
  como "otro efecto de color".

### Fusionaria, con perdida dicha

Ninguna fusion es limpia en las seis condiciones. Las unicas que un
producto podria plantearse, y lo que se pierde:

* **`bars` dentro de `combo`, como opcion (`combo` pinta paleta si el
  compas engancha).** Es lo que `bars` ya hace por degradacion. Se
  pierde un nombre en la CLI. Se pierde la posibilidad de forzar
  "quiero el 4x4 o nada" vs "quiero combo y si hay compas, bonus": hoy
  `combo` solo acentua el "1" en brillo, no cambia de color. Si se
  fusiona hacia `combo` sin paleta, se pierde el 4x4 de billie (media
  0.183, 80% del tema). **Yo no lo fusionaria.** Lo dejaria, y diria
  en la cara del usuario: en house plano se ve igual que `combo`.
* **`beat_flash` como `combo` con color congelado.** Visualmente nunca
  se pisan (0.0% identicos). Se perderia el metronomo naranja, que es
  lo unico que deja ver el timing sin que el espectro distraiga. Sirve
  para calibrar latencia a ojo. **No lo fusionaria.** Tampoco lo
  pondria como modo de escuchar musica.

### Lo incomodo, con el numero delante

La mitad de los nombres **no se distinguen en summer.wav**, que es uno
de los dos temas con los que se afina:

* `roles` 1ch = `combo` el **100%** de los frames
* `bars` = `combo` el **83.2%** de los frames
* `harmony` comparte receta de color con `spectrum` el 100% del tema
  (mix 0), y aun asi solo el 22.3% de los frames son indistinguibles
  por el brillo

Eso no autoriza a borrar `bars` ni `harmony`. Autoriza a no venderlos
como "ocho shows". Son ocho nombres, cinco luces en house, y siete
luces el dia que el compas y la armonia enganchan.

---

## 4. Que NO tocaria, y por que

* **`bars`.** Identico a `combo` en summer. Distinto en billie y en
  bateria con downbeat. Borrarlo porque summer no tiene metrica es
  optimizar para el WAV donde la feature no puede existir.
* **`harmony`.** Identico-en-color a `spectrum` solo cuando no hay
  tonalidad. En synth_tonal la media es 0.77. Es el modo del acorde.
  El material del usuario hoy es mezcla densa; el modo no es culpable.
* **`sustain`.** Identico-en-la-practica a `combo` solo en billie, y
  ni siquiera ahi (onsets). En summer, que es donde se calibro, es
  distinto a proposito (60.1% de mezcla).
* **`spectrum`.** Nunca colapsa con `combo`. Quitar el modo sin ritmo
  deja sin herramienta cuando el PLL se inventa un tempo (el pad a
  170 BPM).
* **`beat_flash`.** Cero overlap con todos. Es pobre como show y util
  como reloj visual. No es redundante; es estrecho.
* **`idle`.** Automatico en silencio. Si se borra el nombre, el
  automatico sigue haciendo falta.
* **`roles` como compositor.** Fusionarlo con `combo` perderia el
  unico modo que aprovecha pared contra techo. Fusionarlo con
  `harmony` perderia el pulso en la pared. No es un duplicado: es
  los dos a la vez, en luces distintas.

La regla practica: un modo que se apaga en el material del usuario
puede ser el unico que sirve con otro. `bars`, `harmony` y `sustain`
estan en esa categoria, cada uno por una senal distinta (compas,
tonalidad, sostenimiento). Los tres se midieron distintos en la
condicion sintetica que enciende esa senal. Conservarlos. Documentar
cuando no hacen nada.
