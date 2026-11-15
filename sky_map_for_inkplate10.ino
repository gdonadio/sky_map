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

// Local times to show the new map (GitHub makes the sunrise map overnight
// and the sunset map during the day).
const int REFRESH_TIMES[][2] = {{5, 30}, {16, 30}};
const int NUM_REFRESH_TIMES = sizeof(REFRESH_TIMES) / sizeof(REFRESH_TIMES[0]);
const unsigned long RETRY_MS = 10UL * 60UL * 1000UL;   // retry a failed load every 10 min

int lastLoadedSlot = -2;          // which refresh time was last loaded successfully
unsigned long lastAttemptMillis = 0;
unsigned long lastTimeSyncMillis = 0;

// Identifies the most recent refresh time that has passed, e.g. "today 16:30".
// Returns -1 before the first refresh time of the day.
int currentSlot(const struct tm& t)
{
  int nowMinutes = t.tm_hour * 60 + t.tm_min;
  int slot = -1;
  for (int i = 0; i < NUM_REFRESH_TIMES; i++)
  {
    if (nowMinutes >= REFRESH_TIMES[i][0] * 60 + REFRESH_TIMES[i][1]) slot = i;
  }
  return slot < 0 ? -1 : t.tm_yday * NUM_REFRESH_TIMES + slot;
}

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
    lastLoadedSlot = currentSlot(timeinfo);
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

  // Load the new map once each refresh time passes (5:30 AM, 4:30 PM).
  // If the load fails, try again every 10 minutes until it works.
  int slot = currentSlot(timeinfo);
  if (slot >= 0 && slot != lastLoadedSlot)
  {
    if (lastAttemptMillis == 0 || millis() - lastAttemptMillis > RETRY_MS)
    {
      lastAttemptMillis = millis();
      if (loadImage())
      {
        lastLoadedSlot = slot;
        lastAttemptMillis = 0;
      }
    }
  }

  delay(1000);
}