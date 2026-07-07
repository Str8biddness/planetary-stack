#pragma once

#include <vector>
#include <cmath>
#include <memory>
#include "geometric_engine.hpp"

namespace zo {

/**
 * GeometricOptics - Optimizes digital camera math using 5-Axis Geometric methodology.
 * Directly maps optical sensor data to [X, Y, Z, Phase, Scale].
 */
class GeometricOptics {
public:
    struct CameraParams {
        float focal_length;    // f (mm)
        float aperture;        // f-number
        float sensor_width;    // mm
        float sensor_height;   // mm
        int px_width;
        int px_height;
    };

    GeometricOptics(std::shared_ptr<GeometricEngine> engine, CameraParams params);

    /**
     * Projects a raw pixel coordinate and metadata into a 5-Axis vector.
     * @param x, y Pixel coordinates
     * @param rgb Color triplet [0-255]
     * @param depth_estimate Optional depth from sensor/lidar
     */
    GeometricVector pixel_to_geometric(int x, int y, const float rgb[3], float depth_estimate = 0.0f);

    /**
     * Geometric Autofocus: Calculates the optimal focus Z-coordinate 
     * using Constructive Interference of high-frequency spatial patterns.
     */
    float calculate_focus_resonance(const std::vector<GeometricVector>& frame_sample);

    /**
     * Inverse Projection: Maps a Geometric Vector back to a "Virtual Pixel"
     * for image generation purposes.
     */
    void geometric_to_pixel(const GeometricVector& vec, int& out_x, int& out_y, float out_rgb[3]);

private:
    std::shared_ptr<GeometricEngine> engine_;
    CameraParams params_;

    // Helper: Mappings for Axis 4 (Phase) based on RGB frequency
    float rgb_to_phase(const float rgb[3]);
};

} // namespace zo
