- Start kalibratie met live preview:
```
python calibration.py --live --output "calib_out" --dict DICT_4X4_50 --marker-length 0.045 --cube-length 0.045 --interval 0.03 --keep-preview-open
```

- Start kalibratie zonder live preview:
```
python calibration.py --live --no-preview --output "calib_out" --dict DICT_4X4_50 --marker-length 0.045 --cube-length 0.045 --interval 0.03
```

- Live kalibratie met extra instellingen (min images, fps, resolutie):
```
python calibration.py --live --output "calib_out" --dict DICT_4X4_50 --marker-length 0.045 --cube-length 0.045 --min-images 20 --max-seconds 90 --interval 0.03 --color-res 1280x720 --fps 30 --keep-preview-open
```

- Live kalibratie met frames opslaan:
```
python calibration.py --live --output "calib_out" --dict DICT_4X4_50 --marker-length 0.045 --cube-length 0.045 --interval 0.03 --save-frames "data/frames"
```

- Kalibratie vanuit opgeslagen afbeeldingen:
```
python calibration.py --images "data/*.png" --output "calib.json" --dict DICT_4X4_50 --marker-length 0.045 --cube-length 0.045
```

- Kalibratie met specifieke marker IDs (komma gescheiden):
```
python calibration.py --live --output "calib_out" --dict DICT_4X4_50 --marker-length 0.045 --cube-length 0.045 --ids "0,1,2,3,4,5" --interval 0.03
```