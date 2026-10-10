# Cloudflare R2: downloads and updates

Every release is served from a Cloudflare R2 bucket: the `.dmg` people
download, `latest.json` the website shows, and `appcast.xml`, the feed
installed apps check for updates. This page sets it up and keeps an eye on
what it costs. How a release is made is in [`releasing.md`](releasing.md).

## What it costs

R2 has a free allowance every month, and downloads (egress) are always free:

| | Free each month | What uses it here |
|---|---|---|
| Storage | 10 GB-month | one `.dmg` (about 35 MB) and two small files |
| Class A operations (writes, lists) | 1 million | about 4 per release |
| Class B operations (reads) | 10 million | every download, and every update check an installed app makes |

Class B is the one that grows. Each installed app checks the feed about once a
day, so 10 million reads a month is roughly 300,000 apps checking daily. Past
the allowance it is $0.36 per million reads.

R2 asks for a card to turn it on, even on the free allowance.

## Set up Cloudflare

You need a domain on Cloudflare. The bucket's free `r2.dev` address is rate
limited and not meant for real traffic, and the feed address is written into
every app, so it has to be one you keep.

1. **R2 → Create bucket**, for example `dictator-downloads`.
2. **Bucket → Settings → Custom Domains → Connect Domain**, for example
   `downloads.example.com`. That address is `DICTATOR_DOWNLOAD_BASE`.
3. **R2 → Manage R2 API Tokens → Create API token**: Object Read & Write,
   limited to that bucket. Note the access key ID and the secret (shown once),
   and the account ID on the R2 overview page.
4. **Workers & Pages → the website → Settings → Builds → Deploy hooks**:
   create one for `main`. That URL is `CF_PAGES_DEPLOY_HOOK`.
5. **The website → Settings → Variables**: `DICTATOR_DOWNLOAD_BASE`, and
   `DICTATOR_SITE_URL` once the site has its address.

## Set up GitHub

In `cc-vb/dictator`, **Settings → Secrets and variables → Actions**:

| Kind | Name | Value |
|---|---|---|
| Variable | `DICTATOR_DOWNLOAD_BASE` | `https://downloads.example.com` |
| Variable | `DICTATOR_SITE_URL` | `https://example.com`, once the website has it |
| Secret | `CF_ACCOUNT_ID` | the account ID |
| Secret | `R2_ACCESS_KEY_ID` | from step 3 |
| Secret | `R2_SECRET_ACCESS_KEY` | from step 3 |
| Secret | `R2_BUCKET` | `dictator-downloads` |
| Secret | `CF_PAGES_DEPLOY_HOOK` | from step 4 |

For releases made from your Mac, put the same names in `.env`.

Decide on `DICTATOR_SITE_URL` before the first release anyone installs. With
it, apps check `https://example.com/appcast.xml`, which the website redirects
into the bucket, so the storage can change later without moving any app.
Without it they check the bucket directly.

## The first release

The website reads `latest.json` from the bucket when it builds, so the first
release has to land before the site's first deploy. Then:

- `https://downloads.example.com/appcast.xml` opens as XML and names the
  version.
- `https://example.com/download/mac` downloads `Dictator-X.Y.Z.dmg`.
- After an update, the app's feed is the one you chose:
  `defaults read /Applications/Dictator.app/Contents/Info SUFeedURL`.

## Usage alerts

Cloudflare's own alerts are in dollars, not in operations, and the free
allowance costs $0. So they tell you when you have gone past the free
allowance, not when you are halfway to it.

**Past the free allowance (built in).** **Manage Account → Billing → Billable
Usage → Create budget alert**, or **Notifications → Add → Budget Alert**.
Set it low, for example $1: any spend at all means the free allowance is
used up. It emails when the projected spend for the month reaches the amount.
It does not stop or cap anything. Cloudflare may already have made one at
$10; lower it.

**Where you are now.** **R2 → the bucket → Metrics** shows storage and
Class A and Class B operations. **Billable Usage** shows what each product
costs this month, R2 included.

**At 50% and 75% of the free allowance.** Cloudflare has no setting for this.
It takes a small scheduled check that reads the month's R2 usage from
Cloudflare's GraphQL analytics API and sends a notification past each
threshold. It is not built yet.

## Moving the storage later

`tools/publish_r2.sh` uploads with the S3 protocol, so any S3-compatible
storage can replace R2. Only the upload address and region in that script
are R2's. With `DICTATOR_SITE_URL` as the feed address, a move is a change of
`DICTATOR_DOWNLOAD_BASE` and the keys, and no app has to move.
