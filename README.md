# screenr
### Emulation of screenshot functionality at Wayback Machine (Archive.org)

Simple web application that uses Python and the Playwright library to create a full-page screenshot of given URL. It functions like the "Save Page Now" feature of the Wayback Machine, but runs on your *my* server.

```
screenr/
├── screenr.py  # The main application file
├── requirements.txt
├── static/
│   └── style.css
└── README.md
```

Playwright library requires browser binaries to function:
```
playwright install
```

