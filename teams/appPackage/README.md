# Teams App Package Notes

1. Replace `${BOT_APP_ID}` in `manifest.json` with the same client ID used by Azure Bot Service.
2. Replace `${BOT_DOMAIN}` with the App Service host name only, for example `bot-app-abc123.azurewebsites.net`.
3. Ensure required icon files are present:
   - `default-color-icon.png` (192x192)
   - `default-outline-icon.png` (32x32)
4. Zip only these root files from this folder:
   - `manifest.json`
   - `default-color-icon.png`
   - `default-outline-icon.png`
5. Upload to Microsoft 365 admin center or Teams Developer Portal in Tenant A.
