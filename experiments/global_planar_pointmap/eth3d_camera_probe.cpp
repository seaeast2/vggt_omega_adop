// Compare Python projection against ETH3D's unmodified standalone implementation.
#include <iostream>
#include <iomanip>
#include "camera.h"
int main() {
  int width, height;
  float p[12];
  if (!(std::cin >> width >> height)) return 1;
  for (float& x : p) std::cin >> x;
  // COLMAP file coordinates use the upper-left pixel corner as origin;
  // the official standalone class expects the center of that pixel as origin.
  p[2] -= .5f; p[3] -= .5f;
  ThinPrismFisheyeCamera camera(width, height, p);
  float x, y;
  std::cout << std::setprecision(12);
  while (std::cin >> x >> y) {
    Vec2f pixel = camera.NormalizedToPixel(Vec2f(x, y));
    std::cout << pixel.x + .5f << " " << pixel.y + .5f << "\n";
  }
}
