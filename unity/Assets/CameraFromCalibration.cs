using UnityEngine;
using System.IO;

namespace Volumetric3D.Unity
{
[System.Serializable]
public class CalibrationRoot
{
    public string timestamp_utc;
    public string world_origin;
    public int camera_count;
    public CalibrationCamera[] cameras;
}

[System.Serializable]
public class CalibrationCamera
{
    public string camera_id;
    public bool success;
    public string message;
    public float[] translation_world_camera;
    public float[] rotation_quaternion_xyzw_world_camera;
    public UnityCalibrationData unity;
}

[System.Serializable]
public class UnityCalibrationData
{
    public float[] translation_world_camera;
    public float[] rotation_quaternion_xyzw_world_camera;
}

public class CameraFromCalibration : MonoBehaviour
{
    public string jsonRelativePath = "../calib_out/final_calibration.json";
    public string rigRootName = "CalibrationRig";
    public string cubeName = "ArUcoCubeOrigin";
    public Vector3 cubeVisualScale = new Vector3(0.09f, 0.09f, 0.09f);
    public string cameraBodySuffix = "_body";
    public string cameraNodeSuffix = "_cam";
    public float importedCameraNearClip = 0.01f;
    public float importedCameraFarClip = 100f;
    public float importedCameraFieldOfView = 60f;
    public float rigGlobalScale = 1f;

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    private static void AutoBootstrap()
    {
        if (FindFirstObjectByType<CameraFromCalibration>() != null)
        {
            return;
        }

        GameObject rigRoot = GameObject.Find("CalibrationRig") ?? new GameObject("CalibrationRig");
        rigRoot.AddComponent<CameraFromCalibration>();
    }

    void Start()
    {
        string fullPath = ResolveCalibrationPath(jsonRelativePath);
        Debug.Log("Loading calibration from: " + fullPath);

        if (!File.Exists(fullPath))
        {
            Debug.LogError("Calibration JSON not found at: " + fullPath);
            return;
        }

        string jsonText = File.ReadAllText(fullPath);

        CalibrationRoot calib = JsonUtility.FromJson<CalibrationRoot>(jsonText);

        if (calib == null || calib.cameras == null)
        {
            Debug.LogError("Failed to parse calibration JSON");
            return;
        }

        Transform rigRootTransform = EnsureRigRoot();
        EnsureCubeOrigin(rigRootTransform);

        rigRootTransform.localScale = Vector3.one * Mathf.Max(0.001f, rigGlobalScale);

        foreach (var camData in calib.cameras)
        {
            ApplyCameraPose(camData, rigRootTransform);
        }
    }

    private void ApplyCameraPose(CalibrationCamera camData, Transform rigRootTransform)
    {
        if (!camData.success)
        {
            Debug.LogWarning("Skipping camera " + camData.camera_id + ": " + camData.message);
            return;
        }

        Vector3 position;
        Quaternion rotation;
        if (!TryExtractUnityPose(camData, out position, out rotation))
        {
            Debug.LogWarning("Skipping camera " + camData.camera_id + ": pose data missing.");
            return;
        }

        Transform cameraGroup = EnsureCameraGroup(camData.camera_id, rigRootTransform);
        Transform cameraNode = EnsureCameraNode(camData.camera_id, cameraGroup);
        EnsureCameraBody(camData.camera_id, cameraGroup);

        Camera unityCamera = cameraNode.GetComponent<Camera>();
        if (unityCamera == null)
        {
            unityCamera = cameraNode.gameObject.AddComponent<Camera>();
        }

        cameraGroup.position = position;

        // Calibration camera conventions are 180 degrees off around X for Unity Camera forward/up.
        rotation *= Quaternion.Euler(180f, 0f, 0f);

        cameraGroup.rotation = rotation;
        ConfigureImportedCamera(unityCamera);

        Debug.Log(camData.camera_id + " loaded from calibration pose.");
    }

    private void ConfigureImportedCamera(Camera unityCamera)
    {
        unityCamera.nearClipPlane = Mathf.Max(0.001f, importedCameraNearClip);
        unityCamera.farClipPlane = Mathf.Max(unityCamera.nearClipPlane + 0.1f, importedCameraFarClip);
        unityCamera.fieldOfView = Mathf.Clamp(importedCameraFieldOfView, 1f, 179f);
    }

    private static string ResolveCalibrationPath(string relativePath)
    {
        string fromAssets = Path.GetFullPath(Path.Combine(Application.dataPath, relativePath));
        if (File.Exists(fromAssets))
        {
            return fromAssets;
        }

        string fromCwd = Path.GetFullPath(relativePath);
        return fromCwd;
    }

    private Transform EnsureRigRoot()
    {
        GameObject root = GameObject.Find(rigRootName);
        if (root == null)
        {
            root = new GameObject(rigRootName);
        }

        return root.transform;
    }

    private void EnsureCubeOrigin(Transform parent)
    {
        GameObject cube = GameObject.Find(cubeName);
        if (cube == null)
        {
            cube = GameObject.CreatePrimitive(PrimitiveType.Cube);
            cube.name = cubeName;
        }

        cube.transform.SetParent(parent, true);
        cube.transform.position = Vector3.zero;
        cube.transform.rotation = Quaternion.identity;
        cube.transform.localScale = cubeVisualScale;
    }

    private static Transform EnsureCameraGroup(string cameraId, Transform rigRootTransform)
    {
        Transform existing = rigRootTransform.Find(cameraId);
        if (existing != null)
        {
            return existing;
        }

        GameObject group = GameObject.Find(cameraId) ?? new GameObject(cameraId);
        group.transform.SetParent(rigRootTransform, true);
        return group.transform;
    }

    private Transform EnsureCameraNode(string cameraId, Transform cameraGroup)
    {
        string cameraNodeName = cameraId + cameraNodeSuffix;
        Transform node = cameraGroup.Find(cameraNodeName);
        if (node == null)
        {
            GameObject existingNode = GameObject.Find(cameraNodeName);
            GameObject nodeObj = existingNode ?? new GameObject(cameraNodeName);
            nodeObj.transform.SetParent(cameraGroup, true);
            node = nodeObj.transform;
        }

        node.localPosition = Vector3.zero;
        node.localRotation = Quaternion.identity;
        node.localScale = Vector3.one;
        return node;
    }

    private void EnsureCameraBody(string cameraId, Transform cameraGroup)
    {
        string bodyName = cameraId + cameraBodySuffix;
        Transform bodyTransform = cameraGroup.Find(bodyName);
        GameObject bodyObj;
        if (bodyTransform == null)
        {
            GameObject existingBody = GameObject.Find(bodyName);
            bodyObj = existingBody ?? GameObject.CreatePrimitive(PrimitiveType.Sphere);
            bodyObj.name = bodyName;
            bodyObj.transform.SetParent(cameraGroup, true);
        }
        else
        {
            bodyObj = bodyTransform.gameObject;
        }

        bodyObj.transform.localPosition = Vector3.zero;
        bodyObj.transform.localRotation = Quaternion.identity;
        bodyObj.transform.localScale = cubeVisualScale;
    }

    private static bool TryExtractUnityPose(CalibrationCamera camData, out Vector3 position, out Quaternion rotation)
    {
        float[] t = null;
        float[] q = null;

        if (camData.unity != null)
        {
            t = camData.unity.translation_world_camera;
            q = camData.unity.rotation_quaternion_xyzw_world_camera;
        }

        if ((t == null || t.Length < 3) && camData.translation_world_camera != null && camData.translation_world_camera.Length >= 3)
        {
            t = camData.translation_world_camera;
        }

        if ((q == null || q.Length < 4) && camData.rotation_quaternion_xyzw_world_camera != null && camData.rotation_quaternion_xyzw_world_camera.Length >= 4)
        {
            q = camData.rotation_quaternion_xyzw_world_camera;
        }

        if (t == null || t.Length < 3 || q == null || q.Length < 4)
        {
            position = Vector3.zero;
            rotation = Quaternion.identity;
            return false;
        }

        position = new Vector3(t[0], t[1], t[2]);
        rotation = new Quaternion(q[0], q[1], q[2], q[3]);
        return true;
    }
}
}