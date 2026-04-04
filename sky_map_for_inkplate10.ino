#include "Inkplate.h"
#include "WiFi.h"
#include "time.h"

Inkplate display(INKPLATE_3BIT);

// ======== CHANGE THESE ========
const char* WIFI_SSID = "wifinetwork";
const char* WIFI_PASS = "wifipassword";

const char* IMAGE_URL =
  "https://raw.githubusercontent.com/gdonadio/sky_map/main/output/sky_map_bw.png";

const char* TZ_INFO = "EST5EDT,M3.2.0/2,M11.1.0/2";
// ==============================

int lastRefreshHour = -1;
int lastRefreshMinute = -1;
unsigned long lastTimeSyncMillis = 0;

void showMessage(const char* msg)
{
  display.clearDisplay();
  display.setTextSize(2);
  display.setCursor(20, 40);
  display.println(msg);
  display.display();
}

void connectWifi()
{
  WiFi.mode(WIFI_MODE_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  showMessage("Connecting WiFi...");

  while (WiFi.status() != WL_CONNECTED)
  {
    delay(500);
  }

  showMessage("WiFi connected!");
  delay(1000);
}

void ensureWifi()
{
  if (WiFi.status() == WL_CONNECTED) return;

  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  showMessage("Reconnecting WiFi...");

  while (WiFi.status() != WL_CONNECTED)
  {
    delay(500);
  }

  showMessage("WiFi connected!");
  delay(1000);
}

bool syncClock()
{
  configTzTime(TZ_INFO, "pool.ntp.org", "time.nist.gov");

  struct tm timeinfo;
  int tries = 0;

  while (!getLocalTime(&timeinfo) && tries < 20)
  {
    delay(500);
    tries++;
  }

  if (tries < 20)
  {
    lastTimeSyncMillis = millis();
    return true;
  }

  return false;
}

bool loadImage()
{
  ensureWifi();

  display.clearDisplay();
  display.setTextSize(2);
  display.setCursor(20, 40);
  display.println("Loading image...");
  display.display();

  bool ok = display.drawImage(IMAGE_URL, 0, 0, false, false);

  if (!ok)
  {
    display.clearDisplay();
    display.setCursor(20, 40);
    display.println("Image FAILED");
    display.display();
    return false;
  }

  display.display();
  return true;
}

void setup()
{
  display.begin();
  display.setRotation(0);

  connectWifi();

  if (!syncClock())
  {
    showMessage("Time sync FAILED");
    return;
  }

  loadImage();

  struct tm timeinfo;
  if (getLocalTime(&timeinfo))
  {
    lastRefreshHour = timeinfo.tm_hour;
    lastRefreshMinute = timeinfo.tm_min;
  }
}

void loop()
{
  // Re-sync clock every 6 hours
  if (millis() - lastTimeSyncMillis > 21600000UL)
  {
    syncClock();
  }

  struct tm timeinfo;
  if (!getLocalTime(&timeinfo))
  {
    delay(5000);
    return;
  }

  int h = timeinfo.tm_hour;
  int m = timeinfo.tm_min;
  int s = timeinfo.tm_sec;

  // Refresh once near :00 and once near :30
  if ((m == 0 || m == 30) && s < 10)
  {
    if (!(h == lastRefreshHour && m == lastRefreshMinute))
    {
      if (loadImage())
      {
        lastRefreshHour = h;
        lastRefreshMinute = m;
      }
    }
  }

  delay(1000);
}