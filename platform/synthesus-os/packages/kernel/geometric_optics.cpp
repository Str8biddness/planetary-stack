#include "geometric_optics.hpp"
#include <algorithm>

namespace zo {

GeometricOptics::GeometricOptics(std::shared_ptr<GeometricEngine> engine, CameraParams params)
    : engine_(engine), params_(params) {}

float GeometricOptics::rgb_to_phase(const float rgb[3]) {
    // Standard RGB to Hue mapping (simplified for Axis 4 / Phase)
    float r = rgb[0] / 255.0f;
    float g = rgb[1] / 255.0f;
    float b = rgb[2] / 255.0f;

    float max = std::max({r, g, b});
    float min = std::min({r, g, b});
    float h = 0;

    if (max == min) return 0;
    if (max == r) h = (g - b) / (max - min);
    else if (max == g) h = 2.0f + (b - r) / (max - min);
    else h = 4.0f + (r - g) / (max - min);

    h /= 6.0f;
    if (h < 0) h += 1.0f;
    return h; // Normalized Hue as Phase
}

GeometricVector GeometricOptics::pixel_to_geometric(int x, int y, const float rgb[3], float depth_estimate) {
    GeometricVector vec;

    // Axis 1 & 2: Normalized Spatial Position
    vec[0] = static_cast<float>(x) / params_.px_width;
    vec[1] = static_cast<float>(y) / params_.px_height;

    // Axis 3: Depth (Z)
    // If no depth estimate, use focal math to guess resonance
    if (depth_estimate == 0.0f) {
        vec[2] = 0.5f; // Center of focal range
    } else {
        vec[2] = std::clamp(depth_estimate / 10000.0f, 0.0f, 1.0f); // Map 0-10m to 0-1
    }

    // Axis 4: Phase (Color Frequency)
    vec[3] = rgb_to_phase(rgb);

    // Axis 5: Scale (Luminance / Intensity)
    float luminance = (0.299f * rgb[0] + 0.587f * rgb[1] + 0.114f * rgb[2]) / 255.0f;
    vec[4] = std::clamp(luminance, 0.0f, 1.0f);

    return vec;
}

float GeometricOptics::calculate_focus_resonance(const std::vector<GeometricVector>& frame_sample) {
    if (frame_sample.empty()) return 0.5f;

    // Sum the high-frequency Phase shifts (Axis 4) across spatial coordinates
    // Maximum constructive interference indicates the 'sharpest' depth.
    float total_interference = 0.0f;
    for (size_t i = 1; i < frame_sample.size(); ++i) {
        float phase_diff = std::abs(frame_sample[i][3] - frame_sample[i-1][3]);
        float scale_res = frame_sample[i][4] * frame_sample[i-1][4];
        total_interference += (phase_diff * scale_res);
    }

    return std::clamp(total_interference / frame_sample.size(), 0.0f, 1.0f);
}

void GeometricOptics::geometric_to_pixel(const GeometricVector& vec, int& out_x, int& out_y, float out_rgb[3]) {
    out_x = static_cast<int>(vec[0] * params_.px_width);
    out_y = static_cast<int>(vec[1] * params_.px_height);

    // Basic Phase-to-RGB conversion (Inverse Hue)
    float h = vec[3] * 6.0f;
    float s = 0.8f; // Constant saturation for synthetic gen
    float v = vec[4]; // Luminance as Value
    
    float c = v * s;
    float x = c * (1 - std::abs(std::fmod(h, 2.0f) - 1));
    float m = v - c;

    float r=0, g=0, b=0;
    if (h < 1) { r=c; g=x; }
    else if (h < 2) { r=x; g=c; }
    else if (h < 3) { g=c; b=x; }
    else if (h < 4) { g=x; b=c; }
    else if (h < 5) { r=x; b=c; }
    else { r=c; b=x; }

    out_rgb[0] = (r + m) * 255.0f;
    out_rgb[1] = (g + m) * 255.0f;
    out_rgb[2] = (b + m) * 255.0f;
}

} // namespace zo
