# Analytics EN — 2026-09-05

## ERRO
```
<HttpError 403 when requesting https://youtubeanalytics.googleapis.com/v2/reports?ids=channel%3D%3DMINE&startDate=2024-01-01&endDate=2026-09-05&metrics=estimatedMinutesWatched%2Cviews%2CaverageViewDuration&alt=json returned "YouTube Analytics API has not been used in project 489505243008 before or it is disabled. Enable it by visiting https://console.developers.google.com/apis/api/youtubeanalytics.googleapis.com/overview?project=489505243008 then retry. If you enabled this API recently, wait a few minutes for the action to propagate to our systems and retry.". Details: "[{'message': 'YouTube Analytics API has not been used in project 489505243008 before or it is disabled. Enable it by visiting https://console.developers.google.com/apis/api/youtubeanalytics.googleapis.com/overview?project=489505243008 then retry. If you enabled this API recently, wait a few minutes for the action to propagate to our systems and retry.', 'domain': 'usageLimits', 'reason': 'accessNotConfigured', 'extendedHelp': 'https://console.developers.google.com'}]">
```
Causa: token sem escopo yt-analytics.readonly
