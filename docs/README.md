# Documentos de analisis

No son documentacion de uso: son la EVIDENCIA sobre la que se tomaron las
decisiones de calibracion del proyecto. Cada umbral que hay en `config.yaml`
sale de una medicion que esta aqui.

Se conservan porque un numero sin su medicion es indistinguible de un numero
elegido a ojo, y este repo ya se comio dos veces el coste de descubrirlo tarde.

| Documento | Que responde | Estado |
|---|---|---|
| `modos-actuales.md` | Que hace cada modo, de que senal vive y **cuando decepciona** | **parcialmente superado** |
| `modos-redundantes.md` | Matrices de distancia RGB: que modos son la misma luz con otro nombre | vigente como evidencia |
| `taxonomia-looks.md` | Los tres ejes (color / brillo / enganche), solapes y huecos | vigente como evidencia |
| `senales-disponibles.md` | Que pide un diseno ambicioso, que existe, que cuesta y que es imposible | vigente |
| `coordinacion-dos-focos.md` | Matriz de pares de looks: consistente, redundante o conflictivo | vigente como evidencia |
| `capa-de-salida.md` | Como se calcula el brillo por canal, y por que los numeros no se comportan como parecen | vigente |
| `dos-luces.md` | Analisis de diseno previo a la capa de composicion | **parcialmente superado** |

`dos-luces.md` propone `wall_channel`/`ceiling_channel` y un modo `dual` que ya
no existen; la configuracion real es `channel_modes`. Su analisis de fondo
—geometria, riesgos perceptuales, que descartar— sigue siendo valido.

**"Vigente como evidencia"** quiere decir que las mediciones valen y las
conclusiones se tomaron a partir de ellas, pero el inventario de looks que
citan ya no es el de `main`: miden `bars`, `beat_flash` y `harmony_energy`,
retirados por redundantes, y `taxonomia-looks.md` propone `harmony_energy`
como hueco a llenar. Se conservan porque una decision sin su medicion es
indistinguible de una tomada a ojo, no porque describan el estado actual.

`modos-actuales.md` esta **parcialmente superado**: la seccion de `spectrum`
se actualizo con la paleta corta, pero el resto sigue describiendo el
inventario viejo. Lleva el aviso en su cabecera.

## Material de referencia

Las mediciones se hacen sobre ocho WAV de 25 s que NO estan versionados
(kobosil, malugi, calvin, kendrick, daddy, travis, summer, billie). Cubren hard
techno, hard dance, pop EDM, rap, reggaeton, trap, house y pop de los 80.

Para reproducir cualquier tabla: `run.py profile --start 5 --duration 25 *.wav`
