# Inventario de senales para composicion con dos luces

## Alcance y criterio

Este documento responde a una pregunta concreta: con una pared izquierda como
acento lateral (canal 0) y un techo como ambiente (canal 1), que puede decidir
la luz a partir del audio hoy, que se puede anadir sin otra FFT y que pide una
pieza de analisis nueva. No presupone mas focos ni geometria estereo.

La distincion importante es esta:

* **Disponible hoy** significa que un efecto puro recibe la senal por
  `AudioState` o `RenderContext`, sin estado propio.
* **Barata** reutiliza el `Frame` de la FFT que ya calcula
  `SpectralAnalyzer`; no abre otro stream ni otra transformada. Los tamanos
  son estimaciones de codigo de produccion, sin contar tests ni documentacion.
* **Cara** necesita una ventana larga, un modelo temporal o una definicion
  musical que hoy no existe. Que sus ingredientes existan no la convierte en
  una senal fiable.

El techo llena el cuarto y la periferia visual. Por eso un pico rapido que se
tolera en la pared no se debe trasladar automaticamente al techo: a 120 BPM y
50 fps la envolvente de beat puede saltar 0.150 de brillo por frame, frente al
limite de 0.03 que el proyecto usa para que no se lea como parpadeo.

## Medicion de referencia

Los rangos siguientes se midieron recorriendo `summer.wav` y `billie.wav` con
`AnalysisEngine`, configuracion por defecto, bloques de 256 muestras y el
mismo downmix mono que la captura. Se descartan los primeros 6 s para no medir
el arranque de las ventanas. El formato es `min .. max (p05, p50, p95)`.
No son escalas comparables entre canciones: `bands` se normaliza contra su
propio pico adaptativo y `flux` no esta normalizado.

| Campo publicado | summer.wav | billie.wav | Lectura y requisito |
|---|---:|---:|---|
| `bpm` | 127.823 .. 128.043 (127.829, 128.005, 128.043) | 116.597 .. 117.176 (116.606, 116.755, 117.175) | Tempo ya estable. Usar solo si `locked`; fue 100% tras el calentamiento en ambos. |
| `confidence` | 0.286 .. 1.000 (0.323, 0.494, 1.000) | 1.000 .. 1.000 | Confianza del tempo, no energia ni estructura de compas. `BeatClock` no acepta estimaciones bajo 0.15. |
| `flux` | 0.108 .. 1.055 (0.162, 0.216, 0.301) | 0.073 .. 1.935 (0.151, 0.221, 0.657) | Novedad espectral instantanea; util para ataques, no para volumen. |
| `bands[0]` graves 20-250 Hz | 0.389 .. 1.000 (0.588, 0.802, 0.965) | 0.115 .. 0.981 (0.194, 0.379, 0.794) | Nivel normalizado y suavizado, no subgrave separado. |
| `bands[1]` medios 250-2000 Hz | 0.466 .. 1.000 (0.667, 0.876, 0.984) | 0.078 .. 0.966 (0.158, 0.363, 0.799) | Nivel normalizado y suavizado. |
| `bands[2]` agudos 2-16 kHz | 0.365 .. 1.000 (0.516, 0.861, 0.986) | 0.074 .. 0.999 (0.146, 0.364, 0.939) | Nivel normalizado y suavizado. |
| `rms` | 0.007 .. 0.062 (0.015, 0.029, 0.045) | 0.004 .. 0.402 (0.013, 0.062, 0.158) | Energia general cruda de un bloque de 5.3 ms: demasiado nerviosa para brillo directo. |
| `chroma_hue` | 0.014 .. 0.984 (0.185, 0.620, 0.775) | 0.469 .. 0.966 (0.550, 0.693, 0.918) | Angulo circular: minimo/maximo no implican un barrido largo. Es color armonico solo si la tonalidad lo avala. |
| `tonality` | 0.019 .. 0.073 (0.021, 0.039, 0.071) | 0.022 .. 0.036 (0.023, 0.030, 0.035) | Ambos quedan bajo `harmony_min_tonality=0.08`; con defaults, `harmony` cae mayormente a color espectral. |
| `sustain` | 0.258 .. 0.988 (0.308, 0.753, 0.981) | 0.000 .. 0.000 | Textura temporal, no armonicidad. Debe cruzarse con `tonality` para el modo actual. |
| `last_onset_time`, `last_onset_strength` | 37 golpes fuera de beat, 1.95/s | 38 golpes fuera de beat, 2.00/s | El instante y fuerza existen; la densidad no se publica. El conteo usa los cambios de `last_onset_time`. |

La medicion del compas confirma que hay que tratarlo como opcional:

| Senal de `BarTracker` | summer.wav | billie.wav | Consecuencia |
|---|---:|---:|---|
| confianza tras 6 s, p05 / p50 / p95 / max | 0.027 / 0.055 / 0.141 / 0.222 | 0.095 / 0.151 / 0.302 / 0.337 | El umbral de entrada es 0.14 y el de salida 0.07. |
| estado final | 0.046, sin enganche | 0.133, sigue enganchado por histeresis | `summer` se engancho solo 14.7% del tramo y luego cayo; no es base para una frase. `billie` estuvo enganchado 100%, pero sigue siendo ambiguo entre 1 y 3. |

`bar_phase`, `phrase_phase` y `beat_in_bar` llegan a `RenderContext` solo
cuando `bar_locked=True`; si no, `cli/sync.py` los deja en sus defaults. En
cambio, la fase del beat se puede consultar con `clock.phase(now)` siempre que
el reloj este enganchado. El selftest previo del proyecto mide 1.8--10.8 ms de
error de prediccion de la rejilla: es la base apropiada para anticipar un beat,
no para reaccionar tarde a un onset.

## Inventario de las caracteristicas pedidas

| Caracteristica musical | Clasificacion | Senal, coste y limite real |
|---|---|---|
| BPM | Disponible hoy | `AudioState.bpm`, `locked`, `confidence` y `RenderContext.clock`. El PLL predice fase y proximo beat; con `locked=False` se debe degradar a brillo fijo. |
| Energia general | Disponible hoy, con cautela | `AudioState.rms` es RMS crudo por bloque. Para una reaccion musical estable, usar `max(state.bands)` o anadir un seguidor de RMS analisis-lado; no mapear el RMS de 5.3 ms directo al techo. |
| Graves, medios, agudos | Disponible hoy | `AudioState.bands[0:3]`, con bandas exactamente 20-250, 250-2000 y 2000-16000 Hz. Son buenos pesos visuales relativos, no una medicion absoluta entre temas. |
| Subgrave / 808 | Barata | No hay corte bajo 80 Hz: graves mezcla bajo, kick y 808. En `analysis/odf.py`, la FFT y `freqs` ya existen; anadir mascara 20-80 Hz, `Frame.sub_bass` y un campo publicado cuesta unas 15-25 lineas. Mantener las tres bandas actuales evita cambiar los modos dorados. |
| Fuerza de cada beat | Barata | No se publica. `AnalysisEngine._accumulate_beat_energy` ya guarda el pico crudo de graves del beat en curso para `BarTracker`; falta cerrarlo por beat, normalizarlo con seguidor de pico y publicar `beat_strength` (unas 25-40 lineas). `beat_envelope` actual tiene forma fija: marca cuando cae el beat, no cuanto pego. |
| Confianza del beat | Disponible hoy | `AudioState.confidence` y `locked`. Es saliencia de periodicidad: un pad con bateria puede tener confianza alta; no mide si la musica es energetica ni si es sostenida. |
| Onset individual | Disponible hoy | `last_onset_time` y `last_onset_strength`, con `now_real` para no adelantar un evento que no se puede predecir. El detector retiene solo golpes fuera del beat si el reloj esta enganchado. |
| Densidad de onsets | Barata | Hay eventos en `OnsetDetector.push`, pero no una tasa. Un `deque` de timestamps de 1-4 s, contado antes de filtrar el margen de beat si se quiere densidad total, mas un campo `onset_rate`, cuesta 20-30 lineas en `engine.py`/`state.py`. No confundirla con el ultimo onset persistente. |
| Centroide espectral | Barata | `SpectralAnalyzer.process` ya tiene `spec` y `freqs`. Sumar `freqs * spec / sum(spec)`, anadirlo a `Frame` y publicarlo cuesta 20-30 lineas. Es brillo/timbre, no la nota musical ni un detector de hi-hat. |
| Balance espectral | Disponible hoy, solo grueso | La proporcion de `state.bands` ya alimenta `spectrum_color`; sirve para bajo/medio/agudo relativo. Un tilt o balance fisico fiable debe partir de energia cruda, pues cada banda publicada se normaliza contra su propio pico; eso es una extension barata del mismo `Frame`, no una FFT nueva. |
| Anchura estereo / paneo | Imposible sin cambiar arquitectura | `audio/capture.py:138-141` hace `mean(axis=1)` antes de escribir el ring buffer mono. Al motor no le queda L/R para correlacion, diferencia de energia ni paneo. Hay que conservar canales en captura y `RingBuffer`, definir `AnalysisEngine` multicanal y solo entonces medir mid/side: no es una senal que se pueda recuperar despues. |
| Cambio de frase metrico | Disponible hoy, fragil | `phrase_phase` y `beat_in_bar` permiten una frase fija de 16 beats, pero solo con `bar_locked`. En `summer` no hay disponibilidad sostenida y en `billie` 1/3 puede estar desplazado medio compas. Es calendario metrico, no deteccion de frase musical. |
| Seccion de cancion | Cara | No hay descripcion de largo plazo ni etiqueta de seccion. Harian falta vectores de energia, timbre, cromas y ritmo por compas, una medida de novedad y una maquina de estados causal (del orden de 150-300 lineas mas audio de referencia etiquetado). El `phrase_phase` repetido no detecta verso, estribillo ni puente. |
| Build | Cara si debe ser musical | Una pendiente simple de energia/centroide en 4-8 beats es barata (30-60 lineas, ventana y regresion), pero confunde un verso que sube con un build. Para dispararlo automaticamente con fiabilidad hay que combinar tendencia, densidad de onsets y duracion, con histeresis y casos de prueba de transicion. |
| Drop | Cara si debe ser musical | Puede definirse como salto negativo de varias senales tras un build, pero no hay memoria de ese build ni modelo de seccion. Un umbral de RMS detectaria silencios, no necesariamente un drop. Comparte el detector temporal de build. |
| Breakdown | Cara | Es una reduccion sostenida de instrumentacion, no solo menos RMS: una balada suave puede tener energia baja sin ser breakdown. Requiere tendencia multibanda, densidad de ataques, armonia y una duracion minima; la mono mezcla impide separar instrumentos. |

## Senales adicionales que ya conviene usar

No estaban en la lista inicial, pero diferencian una composicion de una mera
reaccion al volumen:

| Senal | Estado | Uso visual correcto |
|---|---|---|
| `clock.phase(now)`, `time_to_next_beat`, `beat_index` | Disponible hoy | Anticipar subida y desplazar una capa 50-100 ms sin esperar al golpe. No necesita compas. |
| `silent` | Disponible hoy | Transicion segura a `idle`; evita interpretar ruido de fondo como gesto musical. |
| `chroma_hue` + `tonality` | Disponible hoy | Color de acorde y una puerta de fiabilidad. No cuantizar a nota dominante: en una triada el maximo es inestable. |
| `sustain` | Disponible hoy, con reserva | Cambiar un destello por respiracion lenta. Mide envolvente temporal; no identifica un pad ni excluye ruido coloreado por si solo. |
| Generacion de `BeatClock` | Disponible internamente | Todo acumulador por beat debe resetearse al reenganchar o saltar de octava. Es un requisito para una futura fuerza de beat o resumen por frase. |
| Clave, modo mayor/menor, instrumento, voz | No disponible | El hue de chroma no da etiqueta tonal robusta; una clasificacion de timbre o fuente sobre mezcla mono es analisis nuevo y no una extension de tres bandas. |

## Memoria y suavizado: donde deben vivir

Los efectos actuales son funciones puras de `RenderContext`. `RolesEffect`
incluso cachea el resultado por rol y documenta que solo es correcto si el
efecto no conserva estado. Meter un `deque`, integrador o detector de cambio
dentro de un efecto romperia esa propiedad, haria que dos canales con el mismo
rol dependieran del orden de render y debilitara los tests dorados.

La ubicacion correcta de cada clase de memoria es:

| Necesidad | Sitio correcto | Precedente actual |
|---|---|---|
| Suavizar energia o normalizar amplitud | Analisis, publicar un escalar inmutable | `BandLevels` mantiene pico, ataque y release antes de `AudioState.bands`. |
| Ventana de textura o tendencia | Analisis, reset por stream/reenganche cuando corresponda | `SustainDetector` conserva 2.5 s y rampa de 0.75 s; `BarTracker` descarta historia al cambiar la generacion. |
| Color armonico estable | Analisis | `ChromaAnalyzer` suaviza chroma y tonalidad a su frecuencia propia (23.4 fps). |
| Cola visual de un onset | Efecto puro, derivada de timestamp | `last_onset_time` + `now_real` produce una exponencial sin memoria de efecto. |
| Retardo de color real entre luces | Analisis, publicar valor diferido | Guardar 50-100 ms de hue o bandas con timestamps y publicar, por ejemplo, `delayed_hue`. Con chroma la resolucion es 42.7 ms; con bandas es 5.3 ms. Un desplazamiento de fase solo retrasa brillo, no el color que vino del audio. |
| Variante puramente geometrica o fase desplazada | Efecto puro | Consultar `clock.phase(ctx.now - 0.05)` es determinista y conserva lookahead. |

Cambiar `RenderContext` no hace falta para senales de audio nuevas: ya contiene
`state`. La extension de bajo riesgo es siempre analizador con estado -> campo
inmutable de `AudioState` -> efecto puro. La alternativa de introducir estado
en efectos cambia el contrato de `Effect`, invalida el cache de roles y
requiere redefinir los tests de determinismo.

## Ocho composiciones para pared y techo

Estas clasificaciones hablan de disponibilidad de senal. Casi todas necesitan
un efecto/compositor nuevo para devolver dos RGB, pero no necesariamente otro
analizador.

| Composicion | Clasificacion | Ingredientes exactos y veredicto |
|---|---|---|
| 1. Techo con pulso duro; pared retrasada 50-100 ms | Disponible hoy | `clock.phase(ctx.now)` para el techo y la misma fase evaluada en `ctx.now - 0.05`/`-0.10` para la pared. El retardo minimo visible debe superar aproximadamente un paquete Zigbee, ~40 ms. Es tecnicamente simple, pero es la composicion menos recomendable: pone el destello de 0.150/frame en la luz que llena el cuarto. |
| 2. Techo estable; pared con chase de subdivisiones | Disponible hoy | Techo con `HarmonyEffect` o `SpectrumEffect`; pared con `clock.phase` dividido en 2 o 4 y `last_onset_*` como acento adicional. Las subdivisiones son matematicas, no swing ni tresillos detectados. No requiere compas. |
| 3. Rap bass: techo sub/808; pared snare/clap | Parcial: una senal barata y una cara | Techo: nuevo `sub_bass` 20-80 Hz, con ataque/release y suelo alto para no estroboscopar. Pared: `last_onset_*` ya puede acentuar golpes, pero no sabe si son caja, clap, voz o hi-hat. Separar snare/clap de verdad pide clasificador o separacion de fuentes sobre mezcla mono: caro. |
| 4. House groove: techo four-on-the-floor; pared offbeat | Disponible hoy si el usuario el elige | Techo en cada `clock.phase=0`; pared en fase 0.5 o en corcheas. No necesita saber donde cae el 1 del compas. Detectar automaticamente que una pista es house o que realmente tiene four-on-the-floor seria otra tarea temporal, no una propiedad actual. |
| 5. Flow house: techo cambia despacio; pared tono relacionado | Disponible hoy con puerta tonal, mejora barata | `chroma_hue`, `tonality` y un offset circular fijo de hue para la pared. La mejora barata es publicar un hue diferido o con rampa mas lenta para el techo. En los dos WAV medidos la tonalidad no llega al 0.08 por defecto, asi que con la puerta actual hay que degradar a color espectral; no forzar un color armonico de baja confianza. |
| 6. Color chase: el color viaja de una luz a otra | Una senal barata | Un hue relacionado fijo se puede hacer hoy, pero un viaje temporal real requiere historial. Publicar `delayed_hue` o bandas diferidas desde analisis cuesta poco y conserva pureza; usar estado privado del efecto no. Elegir 85 ms para chroma equivale aproximadamente a dos frames de 42.7 ms. |
| 7. Build/drop: suben saturacion, brillo y contraste; el drop los deja caer | Cara para automatizar | Una demo puede usar una pendiente barata de RMS/bandas/centroide, pero un modificador musical necesita detector causal de build/drop con tendencia de varios beats, densidad de onsets, histeresis y degradacion al no haber beat. No existe hoy senal de seccion ni memoria suficiente. |
| 8. Ambient groove: movimiento lento, beat sutil | Disponible hoy, manualmente seleccionado | Techo con `gentle_brightness` limitado a 0.03/frame y color armonico solo si `tonality` abre; pared con `sustain_mix` o una fase de beat de poca profundidad. `sustain` permite la transicion temporal, pero no debe decidir por si solo que el genero es ambient: compresion o ruido estable lo pueden elevar. |

Un patron transversal es sano para esta sala: pared = informacion rapida
(beat, offbeat, subgrave), techo = color o movimiento continuo. Invertirlo es
posible en codigo, pero desperdicia la unica diferencia fisica que hay entre
los dos canales.

## Tres senales a anadir primero

1. **`beat_strength` normalizado por beat (valor/coste: muy alto).** El
   ritmo ya esta resuelto y `_beat_energy` ya existe internamente. Expone la
   diferencia entre un kick ligero y un downbeat pesado sin inventar un
   clasificador. Permite que la pared acentue de verdad y que el techo solo
   respire cuando el golpe lo merece.
2. **`sub_bass` 20-80 Hz (valor/coste: alto).** Sale de la FFT presente y da
   una capa que las tres bandas actuales mezclan. Es la pieza faltante para
   rap/808 y para separar el peso del cuarto de los medios; no exige tocar la
   arquitectura mono.
3. **`onset_rate` de ventana corta (valor/coste: alto).** Los onsets ya se
   detectan, pero una tasa distingue una base densa de golpes aislados y es
   ingrediente comun para contrastar pared/techo, breaks y futuros builds.
   Debe contarse antes del filtro de offbeat y documentar la ventana para que
   no se confunda con la fuerza del ultimo onset.

Dejo para despues centroide y retardo de color: tambien son baratos, pero los
tres primeros abren mas composiciones con la geometria real. Build/drop y
secciones deben esperar a que haya una definicion medible y audio etiquetado;
si se implementan antes, seran umbrales de volumen con nombres mas ambiciosos.
