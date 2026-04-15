# Camera Kalibratie Overdrachtsdocument

Dit document beschrijft hoe de camerakalibratie in dit project werkt, van opname tot gebruik in Unity.

## Inhoudsopgave

- [Projectoverzicht](#projectoverzicht)
- [Doel Van De Kalibratie](#doel-van-de-kalibratie)
- [Technische Architectuur](#technische-architectuur)
- [Projectstructuur](#projectstructuur)
- [Kalibratieproces (Python)](#kalibratieproces-python)
- [Mathematische Achtergrond](#mathematische-achtergrond)
- [Dataformaat En Export](#dataformaat-en-export)
- [Unity Integratie](#unity-integratie)
- [Coordinatensystemen](#coordinatensystemen)
- [Validatie En Testen](#validatie-en-testen)
- [Bekende Problemen](#bekende-problemen)
- [Troubleshooting](#troubleshooting)
- [Verbeteringen En Roadmap](#verbeteringen-en-roadmap)
- [Overdracht En Contact](#overdracht-en-contact)

## Projectoverzicht

De kalibratie is uitgevoerd met Python (OpenCV) voor de berekeningen en Unity (C#) voor visualisatie en verificatie.

De kalibratie zorgt ervoor dat:

- Daadwerkelijke cameraposities worden berekend ten opzichte van de ArUco-cube.
- Cameraparameters consistent worden gebruikt tussen systemen.

## Doel Van De Kalibratie

- Bepalen van intrinsieke parameters.
- Bepalen van extrinsieke parameters.
- Zorgen dat accurate volumetrische opnames mogelijk zijn.

## Technische Architectuur

- Python/OpenCV doet detectie, pose-estimatie en calibratieberekeningen.
- Resultaten worden geexporteerd naar JSON.
- Unity leest de JSON in en visualiseert de camera-opstelling.

## Projectstructuur

```text
/Volumetric-3d (root)
|- calib_out/
|  |- final_calibration.json
|  |- per_frame_estimates.json
|- calibration/
|  |- calibration/
|  |  |- __init__.py
|  |  |- aruco_compat.py
|  |  |- aruco_cube.py
|  |  |- detector.py
|  |  |- multi_camera_calibrator.py
|  |  |- pose_estimation.py
|  |- camera/
|  |  |- __init__.py
|  |  |- base.py
|  |  |- femto_bolt.py
|  |  |- mock_camera.py
|  |- io/
|  |  |- __init__.py
|  |  |- export_json.py
|  |  |- visualization.py
|  |- math3d/
|  |  |- __init__.py
|  |  |- transforms.py
|  |- tools/
|  |  |- __init__.py
|  |  |- smoke_test.py
|  |- calibration_config.json
|  |- config.example.json
|  |- config.py
|  |- main.py
|- unity/
|  |- Assets/
|  |  |- CameraFromCalibration.cs
```

## Kalibratieproces (Python)

### 1. Setup

- Zorg voor een ArUco-cube.
- Kies een cubeformaat van ongeveer 5% tot 15% van het capturevolume.
Voorbeeld: bij een ruimte van 3 m x 3 m x 2.5 m is een cube van 15 cm tot 40 cm geschikt.
- Sluit camera's een voor een aan.
- Wacht met de volgende camera tot de huidige camera zichtbaar is (bijvoorbeeld in Orbbec Viewer).
- Plaats camera's zo dat ze naar hetzelfde punt kijken.
- Plaats de ArUco-cube zodat elke camera minimaal een zijde goed ziet.

### 2. Kalibratiescript Runnen

Pas `calibration_config.json` aan:

- `cube_length`: lengte van de kubuszijden in meter.
Voorbeeld: 9 cm cube wordt `0.09`.
- `marker_length`: lengte van het zwarte markeroppervlak in meter.
Voorbeeld: 7.8 cm wordt `0.078`.
- `face_ids`: mapping van marker-id's naar kubuszijden.
Let op: zet de cube neer met de juiste `bottom`-zijde volgens de mapping.

Voer daarna uit vanaf de projectroot:

```bash
python -m calibration.main --config calibration/calibration_config.json
```

## Mathematische Achtergrond

### Intrinsieke Matrix

De cameramatrix:

```text
[ fx   0  cx ]
[  0  fy  cy ]
[  0   0   1 ]
```

Waar:

- `fx`, `fy`: brandpuntsafstand in pixels.
- `cx`, `cy`: optisch centrum.

## Dataformaat En Export

Voorbeeld JSON:

```json
{
  "camera_matrix": [[...], [...], [...]],
  "rotation_vectors": [...],
  "translation_vectors": [...]
}
```

## Unity Integratie

- Download Unity Hub indien nodig: <https://docs.unity.com/en-us/hub>
- Open Unity Hub en kies Add > Add from disk.
- Selecteer de projectmap en open vervolgens de map `unity`.
- Gebruik de juiste editorversie (bijvoorbeeld `6000.4.1f1`).
- Start de scene met Play en pauzeer om camera-uitlijning te controleren.

## Coordinatensystemen

- Referentiekader is de ArUco-cube.
- Camera-extrinsieken beschrijven rotatie en translatie ten opzichte van dit referentiekader.
- Consistente assen tussen Python-export en Unity-import zijn cruciaal.

## Validatie En Testen

- Controleer of markers stabiel worden gedetecteerd in alle camera's.
- Vergelijk camera-poses over meerdere frames op consistentie.
- Controleer in Unity of camera's logisch gepositioneerd zijn rond de cube.

## Bekende Problemen

- Slechte belichting geeft slechte detectie.
- Motion blur geeft onbruikbare beelden.
- Te weinig variatie in kijkhoeken verlaagt calibratiekwaliteit.
- Verkeerde cubeschaal geeft foutieve metrische uitkomsten.

## Troubleshooting

| Probleem | Oorzaak | Oplossing |
| --- | --- | --- |
| Geen markers gevonden | Slechte belichting | Verbeter het licht |
| Rare projectie in Unity | Verkeerde matrix of as-conventie | Controleer `calibration_config.json` en importlogica |

