# MVP revisión académica de syllabus

Configura Gemini en `.env` con:

```bash
GEMINI_API_KEY=tu_api_key
GEMINI_MODEL=gemini-2.5-flash
```

Configura también la conexión PostgreSQL de Supabase obtenida desde
`Connect > Session pooler`:

```bash
DATABASE_URL=postgresql+psycopg2://postgres.PROJECT_REF:PASSWORD@HOST.pooler.supabase.com:5432/postgres?sslmode=require
SUPABASE_URL=https://PROJECT_REF.supabase.co
SUPABASE_SECRET_KEY=sb_secret_REEMPLAZAR
SUPABASE_STORAGE_BUCKET=Syllabus
```

El bucket debe ser privado y permitir archivos `application/pdf`. La clave
`SUPABASE_SECRET_KEY` se usa solo en el backend y nunca debe exponerse en Vite.

## Ejecutar

```bash
docker compose up
```

Servicios:

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000/api/health

La primera ejecución construye las imágenes automáticamente. Si cambias dependencias, usa:

```bash
docker compose up --build
```

## Variables de entorno

Variables útiles:

- `DATABASE_URL`: conexión SQLAlchemy a PostgreSQL.
- `SUPABASE_URL`: URL del proyecto Supabase.
- `SUPABASE_SECRET_KEY`: clave privada usada únicamente por el backend.
- `SUPABASE_STORAGE_BUCKET`: bucket privado donde se guardan los PDFs.
- `ALLOWED_ORIGINS`: orígenes permitidos por CORS.
- `MAX_UPLOAD_MB`: tamaño máximo del ZIP.
- `AI_REQUEST_TIMEOUT_SECONDS`: timeout por llamada a IA. La IA solo compara JSON estructurados.
- `GEMINI_API_KEY`: API key de Gemini usada por el backend.
- `GEMINI_MODEL`: modelo de Gemini a usar para la comparación.

Usa `.env.example` como referencia. El archivo `.env` local no se versiona.

## Probar el flujo completo

Genera un ZIP de ejemplo:

```bash
python3 samples/generate_sample_zip.py samples/syllabus_demo.zip
```

En Windows también puedes usar `python` si ese es el comando configurado.

Luego:

1. Abre http://localhost:5173.
2. Selecciona `samples/syllabus_demo.zip`.
3. Presiona `Subir ZIP`.
4. Selecciona el curso `2207`.
5. Presiona `Analizar`.

El ejemplo contiene tres NRC de Termodinámica. Dos tienen reglas equivalentes con distinta redacción y un tercero cambia ponderaciones y umbral de eximición. El análisis extrae datos estructurados desde los PDFs y luego usa la IA solo para comparar los JSON por NRC.

## Flujo de análisis

El backend guarda el PDF en el bucket privado de Supabase Storage y usa archivos
temporales para extraer por código los datos relevantes de cada syllabus. En concreto, prioriza:

- Información general de la asignatura.
- Evaluaciones y ponderaciones.
- Requisitos de aprobación.
- Nota final de la asignatura.
- Criterios de eximición y reglas especiales detectadas dentro de esas secciones.

Cada syllabus se transforma primero en un JSON estructurado con metadata, secciones, evidencia breve y advertencias. La IA recibe únicamente esos JSON por NRC y devuelve el reporte comparativo final.

## Formato esperado de archivos

Cada PDF dentro del ZIP debe llamarse:

```text
AÑOSEMESTRE-CARRERA-CODIGOCURSO-NRC-NUMERONRC-NOMBRERAMO.pdf
```

Ejemplo:

```text
202610-ING-2207-NRC-7542-TERMODINAMICA.pdf
```

El sistema extrae:

- Año: `2026`
- Semestre o periodo: `10`
- Carrera: `ING`
- Código del curso: `2207`
- NRC: `7542`
- Nombre del ramo: `TERMODINAMICA`

## Uso de la API

Subir ZIP:

```bash
curl -F "file=@samples/syllabus_demo.zip" http://localhost:8000/api/uploads/zip
```

Listar cursos agrupados:

```bash
curl http://localhost:8000/api/courses
```

Ejecutar análisis de un curso:

```bash
curl -X POST http://localhost:8000/api/courses/1/analyze
```

Consultar último reporte:

```bash
curl http://localhost:8000/api/courses/1/report/latest
```

## Qué guarda la base de datos

- `course_groups`: grupo por año-semestre y código de curso.
- `syllabi`: metadata extraída, referencia del objeto en Storage y texto extraído.
- `analysis_reports`: reporte comparativo por curso.
- `inconsistencies`: alertas por apartado, variable, NRC, gravedad y sugerencia.

## Alcance del análisis

El MVP analiza estos apartados:

- Evaluaciones y Ponderaciones.
- Requisitos de Aprobación.
- Nota Final de la Asignatura.

Variables intentadas:

- Número y tipo de evaluaciones.
- Ponderaciones porcentuales.
- Existencia de examen.
- Requisitos y nota mínima para rendir examen.
- Criterios mínimos de aprobación.
- Condiciones y umbral de eximición.
- Fórmula de cálculo de nota final.

El análisis se ejecuta en dos etapas:

1. El backend extrae por código un JSON estructurado para cada syllabus/NRC.
2. La IA compara esos JSON entre NRC y genera el reporte.

Con dos syllabus, el sistema solo reporta diferencias entre ambos. Con tres o más, intenta detectar el patrón mayoritario y marcar el NRC que más se aleja del grupo.

## Limitaciones del MVP

- No aprueba ni rechaza syllabus.
- No modifica documentos.
- No evalúa calidad pedagógica.
- No analiza bibliografía ni cronograma completo.
- No integra Canvas ni otros sistemas institucionales.
- No incluye OCR; PDFs escaneados o imagen pueden quedar sin texto.
- El análisis depende de la disponibilidad de la API de Gemini y de la validez de `GEMINI_API_KEY`.
- La comparación depende de la calidad del JSON extraído por código.
- No hay autenticación ni roles de usuario.
