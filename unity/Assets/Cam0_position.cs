using UnityEngine;

public class Cam0_position : MonoBehaviour
{
    void Start()
    {
        // Set camera position
        transform.position = new Vector3(
            0.36772844f,
            0.11638511f,
           -0.02462484f
        )* 10f;

        // Set camera rotation (Quaternion x,y,z,w)
        transform.rotation = new Quaternion(
            0.6419814f,
            0.01808077f,
            0.76624737f,
           -0.01994863f
        );

        transform.rotation *= Quaternion.Euler(180f, 0f, 0f);
    }
}