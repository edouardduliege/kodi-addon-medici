# Medici.tv for Kodi

Unofficial Kodi addon for browsing and playing content from [Medici.tv](https://www.medici.tv/).

The addon supports concerts, operas, ballets, documentaries, master classes and jazz, with playback in either audio-only mode or audio + video.

> This is an unofficial community addon. It is not affiliated with, endorsed by, or supported by Medici.tv.

## Features

- Browse Medici.tv content by category:
  - Concerts
  - Operas
  - Ballets
  - Documentaries
  - Master classes
  - Jazz
- Access existing Medici.tv favorites
- Search the Medici.tv catalog
- Pagination for large result sets
- Audio-only playback
- Audio + video playback
- Selectable video quality:
  - Auto (up to 1080p)
  - 1080p
  - 720p
  - 480p
- Rich metadata:
  - title and subtitle
  - synopsis
  - cast
  - venue
  - year
  - duration
  - production
  - available subtitles
  - resolution
  - program / chapters
  - works
- Context menu entry: `Medici.tv information`
- Local token cache with automatic refresh
- Local metadata cache for faster access to rich information
- English and French interface

## Requirements

- Kodi 21 or later
- A valid Medici.tv account
- Internet connection

The addon uses your Medici.tv credentials only to authenticate against the Medici.tv service. Credentials are stored in Kodi's addon settings. Authentication tokens are cached locally in Kodi's addon data directory.

## Installation

### Install from ZIP

1. Download the addon ZIP release.
2. In Kodi, go to:
   `Settings → Add-ons → Install from zip file`
3. Select the downloaded ZIP.
4. Open the addon settings and enter your Medici.tv username and password.

### Manual installation

Clone or download this repository and copy the `plugin.audio.medici` directory into Kodi's addon directory.

## Configuration

Open the addon settings and configure:

- Medici.tv username
- Medici.tv password
- Playback mode:
  - Audio only
  - Audio + video
- Video quality:
  - Auto
  - 1080p
  - 720p
  - 480p

In Auto mode, video playback is limited to 1080p for compatibility with Kodi devices that may not support the highest Medici.tv streams.

## Usage

Open the addon from Kodi's Add-ons section.

The home screen provides access to favorites, content categories and search.

For supported items, open the context menu and select:

`Medici.tv information`

to display the detailed information available from the corresponding Medici.tv page.

## Audio-only mode

Audio-only mode extracts the audio rendition from the Medici.tv HLS stream and plays it through Kodi without loading the video stream.

This is useful for listening to concerts, operas and other performances on audio-focused Kodi systems.

## Rich metadata

The addon retrieves additional metadata from Medici.tv pages when a title is played or when `Medici.tv information` is opened.

Metadata is cached locally for 24 hours to reduce repeated requests. If Medici.tv is temporarily unavailable, an older cached copy may be used as a fallback when available.

## Remote control / Kore

The addon can be browsed and playback can be controlled with Kore.

Some Kodi dialogs, including detailed addon information and settings screens, are displayed on the Kodi device itself rather than inside the Kore app.

Search input also relies on the Kodi interface, so search is less convenient on fully headless systems.

## Known limitations

- Adding or removing Medici.tv favorites from Kodi is not yet supported.
- Search is not optimized for headless use through Kore.
- Some unavailable/offline content handling may be improved in a future version.
- Rich metadata depends on the structure of Medici.tv web pages and may require updates if the website changes.
- Official Medici.tv branding is not included unless permission is granted.

## Privacy and security

- Your Medici.tv username and password remain in Kodi's addon settings.
- Access and refresh tokens are cached only in Kodi's local addon data directory.
- Tokens and credentials are not part of the addon source code and must never be committed to the repository.
- The addon communicates directly with Medici.tv services.

## Development

Repository structure:

```text
kodi-addon-medici/
├── README.md
├── LICENSE
├── PUBLICATION_CHECKLIST.md
├── .gitignore
└── plugin.audio.medici/
    ├── addon.xml
    ├── addon.py
    └── resources/
        └── language/
            ├── resource.language.en_gb/
            │   └── strings.po
            └── resource.language.fr_fr/
                └── strings.po
```

Basic syntax check:

```bash
python -m py_compile plugin.audio.medici/addon.py
```

## License

This addon is released under the MIT License. See `LICENSE` for details.

Medici.tv and related names, trademarks, logos and content belong to their respective owners.
