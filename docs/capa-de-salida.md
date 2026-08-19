# La capa de salida: como se calcula el brillo por canal

## Que responde

Por que `channel_range: [0.0, 0.05]` no se ve veinte veces mas tenue que
`[0.0, 1.0]`, donde esta el suelo util de ese ajuste, y cual es el parametro
que de verdad controla el contraste de un look que pulsa.

Todo lo que sigue esta medido sobre los ocho WAV de referencia a 50 fps, con
3 s de warmup descartados, salvo las tablas analiticas que se indican.

## El orden, que es fijo

```
look -> channel_range -> channel_saturation -> channel_hue_shift
     -> channel_normalize -> recorte cenital -> bridge
```

El recorte va al final para que ninguna normalizacion vuelva a abrir un salto
ya limitado. Los cuatro controles arrancan NEUTROS (`[0,1]`, `1.0`, `0.0`,
`0.0`) y `ceiling_channel` en `null`: describen un montaje fisico concreto y
un default heredado de otro cuarto se lee como si el look fuera raro.

## `channel_range` no multiplica: remapea

```python
brillo  = max(color)                            # lo que dio el look, 0..1
destino = minimo + (maximo - minimo) * brillo   # remapeo lineal
return scale(color, destino / brillo)           # reescala el RGB entero
```

`minimo` y `maximo` son literalmente el brillo de salida cuando el look esta
apagado y cuando esta a tope. No son factores. De ahi los tres regimenes:

| quieres | pones | resultado |
|---|---|---|
| no tocar nada | `[0.0, 1.0]` | `salida = brillo` |
| atenuar por un factor `k` | `[0.0, k]` | `salida = brillo * k` |
| fijar suelo y techo | `[a, c]` | nunca baja de `a`, nunca sube de `c` |

Que reescale el RGB entero por el mismo factor es lo que conserva el matiz y
la saturacion: solo se mueve el brillo. Por eso este control es el unico de
los cuatro que se puede usar sobre una paleta de colores puros sin ensuciarla.

Una ganancia no puede hacer lo que hace `[a, c]` con `a > 0`: multiplicar baja
el pico al mismo tiempo que el suelo. El remapeo separa ambos extremos.

## Lo que hace que los numeros enganen: cada look usa un recorrido distinto

`brillo` no recorre `0..1`. Medido:

| look | min | p10 | p50 | p90 | max | recorrido p10-p90 |
|---|---|---|---|---|---|---|
| `combo` | 0.072 | 0.122 | 0.214 | 0.454 | 0.842 | 0.332 |
| `harmony` | 0.475 | 0.525 | 0.619 | 1.000 | 1.000 | 0.475 |
| `spectrum` | 0.135 | 0.649 | 0.904 | 0.984 | 1.000 | 0.335 |
| `sustain` | 0.061 | 0.087 | 0.164 | 0.421 | 0.831 | 0.334 |
| `wash` | 0.135 | 0.649 | 0.904 | 0.984 | 1.000 | 0.335 |

Dos lecturas que cambian como se configura:

**`spectrum` vive pegado al techo** (mediana 0.904). Para el, `[0, c]` es
practicamente "brillo fijo = c": lo que pongas en `maximo` es lo que se ve casi
todo el tiempo. Sirve de fondo, no de acento.

**`combo` y `sustain` viven abajo** (medianas 0.214 y 0.164) y solo suben en
los golpes. Ahi `maximo` casi no importa, porque casi nunca se alcanza.

`spectrum` y `wash` dan cifras identicas y no es un error de medicion: los dos
producen `max(RGB) = nivel`. Los cinco colores de `idle_color` y de
`spectrum_palette` tienen `max(RGB) = 1.0`, asi que el brillo de salida es
literalmente el nivel del look. Solo difieren en color. Esa propiedad es
deliberada en la paleta: cambiar de color no mueve el brillo, y por tanto el
recorte cenital sigue midiendo la misma escala pase lo que pase.

## Lineal contra percibido: por que hay que dividir por cinco, no por dos

El valor que se envia es lineal. El ojo no lo es; la respuesta es
aproximadamente `percibido = lineal^0.43`. Con `spectrum` (brillo 0.94):

| `maximo` | sale lineal | se percibe | u8 enviado (magenta) | desvio de matiz |
|---|---|---|---|---|
| 1.00 | 0.940 | 0.974 | `(239, 0, 203)` | 0.0deg |
| 0.40 | 0.376 | 0.657 | `(95, 0, 81)` | -0.2deg |
| 0.20 | 0.188 | 0.487 | `(47, 0, 40)` | -0.1deg |
| 0.10 | 0.094 | 0.362 | `(23, 0, 20)` | -1.2deg |
| 0.06 | 0.056 | 0.290 | `(14, 0, 12)` | -0.4deg |
| 0.03 | 0.028 | 0.216 | `(7, 0, 6)` | -0.4deg |
| 0.02 | 0.019 | 0.181 | `(4, 0, 4)` | -9.0deg |
| 0.01 | 0.009 | 0.134 | `(2, 0, 2)` | -9.0deg |

**Para bajar a la mitad lo percibido hay que dividir el numero por unas cinco
veces.** De 0.40 a 0.08, no a 0.20. Eso explica la sorpresa de que `0.05` se
siga viendo como una luz encendida: se percibe alrededor de 0.27, no de 0.05.

**El suelo util esta en 0.03.** Por debajo, la cuantizacion a 8 bits del envio
(`_to_u16`) deja tan pocos pasos que el matiz se rompe: a 0.02 el magenta pasa
a `(4, 0, 4)`, que ya no es magenta sino violeta, con 9 grados de desvio. No
tiene sentido pedir menos de 0.03: se pierde el color sin ganar oscuridad
apreciable.

De paso, comprobado por barrido de 100.001 valores: ninguna salida de
`_to_u16` cae en el rango `1..255` donde vive el fallo de conversion de
`hue-entertainment`. La cuantizacion previa lo evita por construccion, no por
suerte, asi que bajar `beat_floor` a cero no pisa esa mina.

## El contraste no vive en `channel_range`

Si lo que se busca es que un look pulse mas —que se note al prenderse y
apagarse— atenuar el OTRO canal tiene un techo. Lo que fija la profundidad del
pulso de `combo` es `beat_floor`, que es su brillo entre golpes:

| `beat_floor` | min | max | contraste |
|---|---|---|---|
| 0.12 | 0.112 | 0.784 | 7.0x |
| 0.08 | 0.081 | 0.784 | 9.7x |
| 0.04 | 0.050 | 0.784 | 15.5x |
| 0.02 | 0.035 | 0.784 | 22.3x |
| 0.00 | 0.020 | 0.784 | 39.5x |

(Analitico, sobre una fase de beat completa con bandas `(0.9, 0.3, 0.1)`.)

Con el default de 0.12 el pulso solo recorre 7x. Bajarlo a 0.04 lo lleva a
15.5x sin llegar al parpadeo agresivo. `beat_floor` es global, pero apenas toca
a `spectrum`: su nivel lo manda la energia, y pasa de 0.912 a 0.904.

**Aviso.** Con `ceiling_channel: null` no hay ninguna proteccion de pendiente,
y sobre audio real ningun look respeta 0.03 por frame por si solo. Antes de
bajar `beat_floor`, quien tenga una lampara que llene la periferia visual
deberia declararla: es donde mas dispara la fotosensibilidad.

## Los otros tres controles

`channel_saturation` y `channel_hue_shift` se disenaron para mezclas continuas,
donde dar paleta propia a un foco no destruye informacion. **Sobre una paleta de
colores elegidos trabajan en contra.** Con los valores que traia el repo antes
de neutralizarlos (`0.85` y `0.08`):

| color | crudo | tras saturacion 0.85 y hue +0.08 |
|---|---|---|
| rojo | `1.00, 0.00, 0.00` | `1.00, 0.56, 0.15` (naranja, 28.8deg) |
| magenta | `1.00, 0.00, 0.85` | `1.00, 0.15, 0.46` (frambuesa, 337.8deg) |
| azul | `0.00, 0.05, 1.00` | `0.52, 0.15, 1.00` (violaceo, 265.8deg) |

El rojo puro sale naranja. Si se usa `spectrum` en un canal, esos dos controles
tienen que quedarse en `1.0` y `0.0`.

`channel_normalize` acerca el canal a su pico adaptativo. Conserva el matiz
—escala el RGB uniformemente— pero comprime la dinamica, asi que compite con
`channel_range`: si se limita el techo de un canal y ademas se normaliza, la
normalizacion reamplifica lo que el rango acababa de bajar.

## Como calcular, en resumen

1. Elige el look de cada canal y mira su mediana en la tabla de recorrido. Eso
   dice si `maximo` sera "el brillo casi siempre" o "un pico que casi nunca se
   alcanza".
2. Para un canal de fondo con `spectrum`: `brillo visible ~= maximo * 0.90`.
3. Si quieres bajarlo a la mitad de lo PERCIBIDO, divide `maximo` por cinco.
4. No bajes de 0.03: se rompe el matiz sin ganar oscuridad.
5. Si lo que falta es pulso, no sigas atenuando el fondo. Baja `beat_floor`.
