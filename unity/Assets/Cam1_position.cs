using UnityEngine;

public class Cam1_position : MonoBehaviour
{
    void Start()
    {
        // Set camera position
        transform.position = new Vector3(
            0.05270916f,
            0.06192796f,
            0.24002035f
        )* 10f;

        // Set camera rotation (Quaternion x,y,z,w)
        transform.rotation = new Quaternion(
            0.05755512f,
            0.10524021f,
            0.99262476f,
            0.01754828f
        );

        transform.rotation *= Quaternion.Euler(180f, 0f, 0f);
    }
}