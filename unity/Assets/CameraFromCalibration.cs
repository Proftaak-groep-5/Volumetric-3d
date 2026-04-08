using UnityEngine;
using System.IO;
using System.Collections.Generic;

// JSON classes
[System.Serializable]
public class CameraData
{
    public string camera_id;
    public float[] translation_world_camera;
    public float[] rotation_quaternion_xyzw_world_camera;
}

[System.Serializable]
public class CameraDataArray
{
    public CameraData[] cameras;
}

// Main script
public class CameraFromCalibration : MonoBehaviour
{
    public string jsonRelativePath = "../../../calib_out/final_calibration.json"; // vanaf Assets
    public float positionScale = 10f; // optioneel, bv 10x
    public bool spawnCameras = true; // spawn camera objects als ze niet bestaan

    void Start()
    {
        string fullPath = Path.GetFullPath(jsonRelativePath);
        Debug.Log("Looking for calibration file at: " + fullPath);

        if (!File.Exists(fullPath))
        {
            Debug.LogError("Calibration JSON not found at: " + fullPath);
            return;
        }

        string jsonText = File.ReadAllText(fullPath);

        // Wrap JSON array voor JsonUtility
        string wrappedJson = "{\"cameras\":" + jsonText + "}";
        CameraDataArray calib = JsonUtility.FromJson<CameraDataArray>(wrappedJson);

        if (calib == null || calib.cameras == null)
        {
            Debug.LogError("Failed to parse calibration JSON");
            return;
        }

        foreach (var camData in calib.cameras)
        {
            // Zoek of er al een GameObject is met de cameraId
            GameObject camObj = GameObject.Find(camData.camera_id);
            if (camObj == null && spawnCameras)
            {
                camObj = new GameObject(camData.camera_id);
                camObj.AddComponent<Camera>();
            }

            if (camObj != null)
            {
                // Positie toepassen
                camObj.transform.position = new Vector3(
                    camData.translation_world_camera[0],
                    camData.translation_world_camera[1],
                    camData.translation_world_camera[2]
                ) * positionScale;

                // Rotatie toepassen
                Quaternion rot = new Quaternion(
                    camData.rotation_quaternion_xyzw_world_camera[0],
                    camData.rotation_quaternion_xyzw_world_camera[1],
                    camData.rotation_quaternion_xyzw_world_camera[2],
                    camData.rotation_quaternion_xyzw_world_camera[3]
                );

                // OpenCV → Unity mismatch correctie
                rot *= Quaternion.Euler(180f, 0f, 0f);
                camObj.transform.rotation = rot;

                Debug.Log(camData.camera_id + " loaded from calibration.");
            }
        }
    }
}