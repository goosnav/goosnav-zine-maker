# Goosnav Zine Maker

Choose a folder of comics, review the assembled issue, and export it for print or the web. The editor runs locally and saves a portable issue alongside your comics or in a destination you choose.

## Make an issue

1. On macOS, double-click **run.command**. On Windows, open **run.cmd**. The editor opens first. Choose **Open folder…** inside it to select comics and an optional output location. You can also choose **Add essay…** and start typing immediately. When you save your first essay, select the folder for the issue. The packaged macOS download includes its runtime. Launching from source requires uv or Python 3.11 or later and an internet connection for initial setup.
2. The editor sorts comics by filename, finds the artwork on each scan, centers it, and builds a cover from the folder name and first comic. The default trim is **8.5 × 5.5 inches**, the size of the supplied Goosnav issues.
3. Select **Issue setup…** to change the title, trim, comic borders, cover, or page numbering. Choose 9 × 6, 6 × 9, US Letter, or enter a custom width and height from 3 to 24 inches.
4. Choose **Export issue… → Generate editions**. Use **Show export folder** to collect the results. Each export creates a new folder, so you can keep earlier proofs.

You can also drag files into the preview. Use **Edit artwork…** to draw a crop, enter crop percentages, rotate the art, or switch between centered artwork, the entire scan, and a filled frame. Use the Up and Down keys to browse issue pages. The ▲ and ▼ buttons under the list move the selected comic or essay in the reading order. Edits take effect when you click **Apply edits** or **Save**.

## Fit comics to the book

Zine Maker uses Goosnav Comic Maker’s border detector and reading order. It analyzes a small copy of the scan and renders from the original artwork. Existing issues gain automatic panel layouts when opened. A custom whole-page crop, rotation, or framing choice takes precedence over automatic panel layout.

Under **Panel layout…**, review up to ten numbered rectangles. **Automatic** keeps ordinary strips together and divides square grids or stacked panels across consecutive pages. Multi-page comics use plain pages with a small trim margin. Choose two pages, four pages, or one page per panel to control the reading pace. A comic with fewer panels uses fewer pages. To carry a single drawing across the binding, choose **Facing spread**. The editor inserts a blank page when needed to start the spread on the left.

Choose **Find drawn borders** to detect the panels again, or **Find gaps between panels** for unframed drawings. Use **Add panel**, redraw a selected rectangle, or change its reading order before applying. Include any captions or credits you want to print inside the selected area.

## Set an essay

**Edit essay…** controls text size in points, the blackletter initial, and an optional illustration. Text flows down the first column, into the second, and onto continuation pages. Narrow trims use one column. The opening page reserves space for the drawing. Choose its side, width, height, framing, zoom, and focal point. The initial uses the bundled UnifrakturMaguntia font.

Repeated imports of the same essay text produce one essay. If a scan resembles a typeset copy of an essay, **Review possible duplicate essay…** selects the image so you can inspect it and remove it from the issue. Removed source files stay on disk, and rescanning remembers your decision.

## Design a cover

Choose **Add cover…** and select an image with any filename. The cover assistant opens with a proof at the issue’s trim size. You can also select an existing front or back cover and click **Cover assistant…**.

- Choose one of 36 named palettes, including combinations inspired by the Goosnav covers. For new combinations, select a mood and click a four-color suggestion. **More suggestions** gives three more. Suggestions use the artwork’s dominant colors when available.
- Under **Border**, choose **Solid band** or **Two bands** and set the width as a percentage of the shorter page edge. The palette supplies the colors. To override one, select a swatch and click the corresponding band button. **Fill inside border** crops the artwork to fill the frame. **Extend edge colors** fills leftover strips with the outermost pixels and preserves lettering near the edge. **Show entire crop** centers the image on white. Set **Black inner line** in points, or enter zero for a plain border. Artwork zoom and focus change the printed composition.
- **Apply palette wash** tones the artwork with the palette. Under **Filters**, choose grayscale, black ink, nearest palette color, or Floyd–Steinberg dithering. Nearest palette color uses the selected four swatches. Wash strength, saturation, and contrast are independently adjustable.
- Pick a palette color, a color sampled from the original, or a familiar print swatch. Click the proof to fill a connected region with **Paint bucket**. **Replace color** affects matching pixels throughout the artwork. Use **Brush** and drag to paint a stroke. Each stroke can be undone. Increase bucket tolerance for uneven scanned color. Use **Fit page / Zoom** for small areas. The process-color swatches are RGB approximations.
- **Undo**, **Redo**, and **Cancel** let you try changes. **Save cover** stores the settings and paint edits with the issue. Reopen the assistant to revise them or remove the last paint edit. All three exported editions use the saved design and the original file stays intact.

## Source folder

A flat folder of images is enough. Zine Maker reads JPEG, PNG, TIFF, WebP, BMP and GIF images, using the first frame of a multiframe file. UTF-8 TXT and Markdown files become plain-text essays. Each file can be up to 256 MiB, each image up to 100 megapixels, and each essay up to 150,000 characters.

For a mixed issue, you can use the following structure. Every section is optional.

```text
Winter issue/
  cover.jpg
  comics/
    01 - Night shift.tif
    02 - Low tide.png
  essays/
    Letter from the editor.txt
  ads/
    Bookshop.png
  back-cover.jpg
```

On first scan, a supplied cover leads, essays flow across as many pages as necessary, and ads are spaced among the comics. A supplied back cover closes the issue. The scanner reads the top-level folder and the immediate contents of recognized folders, including Comic Maker’s `all-book-prints`. Paired Comic Maker PNG and TIFF book crops are imported once per comic. You can also open a folder of book prints directly. Name loose artwork `cover`, `back-cover`, or `ad-…` to assign its role during import. Use **Edit artwork…** to change it later.

Reopening the comics folder or choosing **Rescan folder** imports new filenames. Existing edits and removed-page decisions are preserved. To replace a previously imported scan, add the updated file with **Add files…**, then remove the old item.

## Output

All issue data is under **Goosnav Zine/** in the comics folder by default. To change the destination in the editor, use **Open folder… → Choose another location…** before opening the issue. Use a separate output folder for each magazine.

| File or folder | Contents |
| --- | --- |
| `issue.json` | Issue settings, page order, essay text, and crop edits |
| `assets/` | Local artwork copies needed to reopen and export the issue |
| `exports/<run>/print.pdf` | Single trim-size pages in reading order, vector text and borders, lossless artwork sampled up to 300 ppi |
| `exports/<run>/digital.pdf` | The same layout with artwork sampled up to 145 ppi |
| `exports/<run>/website/` | Standalone web edition with an HTML reader and page images |

Print the PDF at **Actual size / 100%**. For a folded home booklet, use your PDF viewer’s booklet printing and a sheet size that fits the spread. The print file uses finished trim dimensions and has no added bleed or press marks. For online reading, upload the complete **website** folder to a static host or share **digital.pdf**. The web edition also opens directly from disk.

**Save project file** writes a dated **.gsnvzine** snapshot in the issue folder, including essay illustrations, source artwork, and edits. **Open project…** restores it into a fresh working folder beside the selected snapshot. The original working folder also saves each applied edit automatically. Back up that folder to preserve previous export runs as well. Open this folder directly to resume a moved issue. Originals are read-only inputs. Processing and export work offline after setup. Close the terminal or press Ctrl+C to stop the editor.

## Run from a terminal

Run the launcher from any directory to open the GUI. The editor reads the comics folder you select inside it.

```sh
/path/to/goosnav-zine-maker/run.sh
```

Pass a comics folder (or `.` for the current directory) to open an issue immediately. Add `--export` for a one-command build. Running `--export` alone uses the current directory.

```sh
./run.sh "/path/to/comics" --output "/path/to/winter-issue"
./run.sh "/path/to/comics" --output "/path/to/winter-issue" --export
```

On Windows use `run.cmd` with the same arguments. Linux’s in-editor folder picker uses Tk. Passing a folder path works without a graphical picker.

## macOS download

Run `uv run --frozen --group packaging python scripts/package_macos.py` on the target Mac to build its self-contained ZIP in `dist/`. Extract the ZIP, then double-click **run.command**.

## Verification

```sh
uv run --frozen python -m unittest discover -s tests -v
```

Tests cover strip cropping, natural order, optional content, text pagination, page dimensions, manual edits, reopen, and export. The bundled corner ornaments come from the supplied Goosnav page templates. The title-bar mark and Luna colors follow GSNV Paint. The repository excludes source scans, full reference issues, PSD templates, installed packages, and generated editions.
