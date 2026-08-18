# Factibilidad del detector de compas

## Pregunta y veredicto

**Veredicto: respuesta 2. No vale la pena construir otro detector de compas
con estas senales para este material.** Hay pulsacion y, en algunos temas,
estructura de dos tiempos, pero no aparece una evidencia fiable del "1" de
cuatro. `bars` debe tratarse como un look que solo se activa donde el
`BarTracker` ya encuentra un acento de compas; no hay base medida para una
tarea mayor que intente rescatarlo con chroma, flujo o agudos.

No hay ground truth de downbeat en los ocho WAV, asi que el informe no afirma
que un slot concreto sea el "1" real. Solo pregunta si una candidata se aleja
del reparto plano 25/25/25/25. Aun asi, un reparto concentrado en dos slots
opuestos tampoco resuelve el problema: describe 1/3 frente a 2/4, pero no
permite distinguir el "1" del "3".

## Metodo reproducible

- WAV: `D:\\Work\\research\\hue\\{billie,daddy,travis,calvin,kendrick,kobosil,summer,malugi}.wav`.
- Ventana: desde t=5.0 s hasta t=30.0 s o el final del WAV. Billie y Summer
  duran 25 s, por lo que aportan 20 s; los otros seis aportan 25 s.
- Alimentacion: `engine.feed(block, offset, wall_t=t)`. Cada observacion se
  asigna con `BeatClock.beat_index(engine.mapper.to_wall(t))`, nunca por el
  tiempo absoluto.
- Generaciones: cuando `BeatClock.generation` cambia dentro de la ventana se
  corta el segmento; se informa el segmento consistente mas largo. Asi no se
  mezclan dos rejillas. Los segmentos elegidos contienen: Billie 39 beats,
  Daddy 25, Travis 57, Calvin 27, Kendrick 43, Kobosil 50, Summer 44 y Malugi
  61.
- Concentracion `C`: distancia de variacion total al uniforme, la misma que
  usa `BarTracker`:

  `C = sum(abs(p_i - 0.25)) / 1.5`

  Vale 0 para plano y 1 si toda la masa cae en un slot. Es preferible a
  max/min: una celda cercana a cero haria la razon infinita por ruido de
  muestreo, mientras `C` conserva una escala acotada y ya tiene semantica en
  el codigo.

Las candidatas se calculan sin FFT adicional: graves y agudos son el maximo
de `Frame.bands[0]` y `[2]` en cada beat; flujo es la suma de `Frame.flux`;
chroma es la suma por beat del cambio L1 entre vectores `ChromaAnalyzer.chroma`
consecutivos. `mixta` es el promedio sin pesos de los cuatro repartos ya
normalizados: no introduce una calibracion elegida despues de ver los WAV.

## Control sintetico con ground truth

Se uso `click_track(128, 30, downbeat_accent=3.0)`. El reloj termino en
127.9 BPM y el downbeat conocido corresponde al slot 1 de SU rejilla. La
columna `encuentra` compara el argmax de la candidata con ese slot conocido.

| candidata | p0 | p1 | p2 | p3 | C | encuentra |
|---|---:|---:|---:|---:|---:|---|
| graves | 13.3% | 60.1% | 6.6% | 20.0% | 0.468 | si |
| agudos | 38.6% | 12.4% | 35.8% | 13.2% | 0.325 | no, slot 0 |
| flujo | 26.0% | 25.5% | 24.2% | 24.3% | 0.020 | no, slot 0 |
| croma | 18.0% | 32.1% | 17.7% | 32.2% | 0.191 | no, slot 3 |
| mixta | 24.0% | 32.5% | 21.1% | 22.4% | 0.101 | si |

El control descarta agudos, flujo y cambio de chroma como reemplazos: ni
siquiera localizan el "1" cuando el sintetico lo marca deliberadamente. La
mezcla acierta solo porque incluye graves, pero diluye C de 0.468 a 0.101; no
aporta una fuente independiente de metrica.

## Repartos reales

### Energia de graves por beat (linea base)

| tema | p0 | p1 | p2 | p3 | C |
|---|---:|---:|---:|---:|---:|
| billie | 21.0% | 29.9% | 20.6% | 28.6% | 0.112 |
| daddy | 27.5% | 25.0% | 24.0% | 23.5% | 0.033 |
| travis | 30.4% | 22.6% | 21.2% | 25.9% | 0.083 |
| calvin | 24.4% | 25.6% | 25.6% | 24.3% | 0.017 |
| kendrick | 25.5% | 24.6% | 26.5% | 23.4% | 0.027 |
| kobosil | 26.5% | 25.7% | 24.0% | 23.8% | 0.029 |
| summer | 22.7% | 25.0% | 25.1% | 27.2% | 0.031 |
| malugi | 24.9% | 24.7% | 25.3% | 25.1% | 0.005 |

### Energia de agudos por beat

| tema | p0 | p1 | p2 | p3 | C |
|---|---:|---:|---:|---:|---:|
| billie | 25.7% | 25.1% | 26.4% | 22.9% | 0.029 |
| daddy | 28.4% | 23.8% | 23.6% | 24.2% | 0.046 |
| travis | 23.7% | 22.5% | 27.4% | 26.4% | 0.051 |
| calvin | 24.9% | 26.4% | 26.4% | 22.3% | 0.037 |
| kendrick | 29.9% | 22.3% | 27.4% | 20.4% | 0.098 |
| kobosil | 26.3% | 25.6% | 24.2% | 24.0% | 0.025 |
| summer | 22.7% | 24.2% | 26.3% | 26.7% | 0.041 |
| malugi | 23.0% | 27.6% | 23.7% | 25.7% | 0.044 |

Kendrick es el maximo de esta columna, pero sus dos picos son p0=29.9% y
p2=27.4%: estructura de dos tiempos, no evidencia de cual de ellos es el
downbeat. Ademas agudos falla el control sintetico, donde el argmax cae en la
caja y no en el "1".

### Novedad espectral por beat (flujo)

| tema | p0 | p1 | p2 | p3 | C |
|---|---:|---:|---:|---:|---:|
| billie | 25.4% | 25.9% | 26.0% | 22.8% | 0.029 |
| daddy | 26.0% | 25.0% | 24.2% | 24.8% | 0.014 |
| travis | 25.1% | 24.6% | 25.4% | 24.9% | 0.007 |
| calvin | 23.9% | 26.7% | 26.4% | 23.0% | 0.041 |
| kendrick | 24.0% | 26.8% | 23.8% | 25.5% | 0.030 |
| kobosil | 25.7% | 24.9% | 25.3% | 24.1% | 0.013 |
| summer | 23.6% | 26.1% | 26.3% | 23.9% | 0.033 |
| malugi | 23.1% | 26.8% | 23.8% | 26.3% | 0.041 |

### Cambio de chroma por beat

| tema | p0 | p1 | p2 | p3 | C |
|---|---:|---:|---:|---:|---:|
| billie | 25.3% | 25.3% | 26.8% | 22.7% | 0.030 |
| daddy | 28.6% | 22.8% | 26.0% | 22.7% | 0.061 |
| travis | 23.8% | 27.6% | 22.7% | 25.9% | 0.046 |
| calvin | 22.8% | 23.4% | 25.8% | 28.0% | 0.051 |
| kendrick | 26.2% | 26.9% | 22.6% | 24.3% | 0.042 |
| kobosil | 26.3% | 26.0% | 24.5% | 23.3% | 0.030 |
| summer | 22.9% | 26.8% | 25.5% | 24.8% | 0.031 |
| malugi | 23.8% | 27.4% | 23.5% | 25.3% | 0.036 |

### Mezcla sin pesos

| tema | p0 | p1 | p2 | p3 | C |
|---|---:|---:|---:|---:|---:|
| billie | 24.3% | 26.5% | 24.9% | 24.2% | 0.020 |
| daddy | 27.6% | 24.2% | 24.4% | 23.8% | 0.035 |
| travis | 25.8% | 24.3% | 24.2% | 25.8% | 0.020 |
| calvin | 24.0% | 25.5% | 26.1% | 24.4% | 0.021 |
| kendrick | 26.4% | 25.1% | 25.1% | 23.4% | 0.021 |
| kobosil | 26.2% | 25.5% | 24.5% | 23.8% | 0.023 |
| summer | 23.0% | 25.6% | 25.8% | 25.7% | 0.027 |
| malugi | 23.7% | 26.6% | 24.1% | 25.6% | 0.030 |

La combinacion cancela las desviaciones entre candidatas en vez de reforzar
una estructura comun. Su maximo real es C=0.035 (Daddy), muy por debajo del
control de graves C=0.468 y tambien por debajo de Billie-graves C=0.112.

## Decision para la siguiente ronda

No hay una candidata que satisfaga a la vez las dos condiciones necesarias:

1. localizar el "1" en el sintetico con acento conocido; y
2. mostrar concentracion clara y de cuatro posiciones en los temas reales.

Graves cumple la primera, pero solo Billie muestra una separacion apreciable
en real. Agudos parece prometedor solo en Kendrick, pero falla la primera y
su reparto es par 1/3. Flujo y chroma ni localizan el control ni superan
C=0.061 en los WAV. La mezcla no rescata informacion.

Por tanto se cancela el detector de compas nuevo. El problema no es solo la
senal actual de graves: las cuatro fuentes disponibles carecen de evidencia
reutilizable del downbeat en este conjunto. Invertir en seleccion por genero
seria especulativo porque ninguna candidata valida separa generos con ground
truth. La accion de bajo riesgo es documentar `bars` como dependiente de un
backbeat/acento ya medible y conservar su respaldo espectral cuando no haya
enganche estable.
