# Goosnav Zine Maker

Choose a folder of comics, review the assembled issue, and export it for print or the web. The editor runs locally and saves a portable issue alongside your comics or in a destination you choose.

## Make an issue

1. On macOS, double-click **run.command**. On Windows, open **run.cmd**. The editor opens first. Choose **Open folder…** inside it to select comics and an optional output location. You can also choose **Add essay…** and start typing immediately. When you save your first essay, select the folder for the issue. The packaged macOS download includes its runtime. Launching from source requires uv or Python 3.11 or later and an internet connection for initial setup.
2. The editor sorts comics by filename, finds the artwork on each scan, centers it, and builds a cover from the folder name and first comic. The default trim is **8.5 × 5.5 inches**, the size of the supplied Goosnav issues.
3. Select **Issue setup…** to change the title, trim, comic borders, cover, or page numbering. Choose 9 × 6, 6 × 9, US Letter, or enter a custom width and height from 3 to 24 inches.
4. Choose **Export issue… → Generate editions**. Use **Show export folder** to collect the results. Each export creates a new folder, so you can keep earlier proofs.

You can also drag files into the preview. Use **Edit artwork…** to draw a crop, enter crop percentages, rotate the art, or switch between centered artwork, the entire scan, and a filled frame. Select a page and use the arrows under the list to change the reading order. **Edit essay…** changes the title and body of an essay. Edits take effect when you click **Apply edits** or **Save**.

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

On first scan, a supplied cover leads, essays flow across as many pages as necessary, and ads are spaced among the comics. A supplied back cover closes the issue. The scanner reads the top-level folder and the immediate contents of recognized folders, including Comic Maker’s `all-book-prints`. Paired Comic Maker PNG and TIFF book crops produce one page per comic. You can also open a folder of book prints directly. Name loose artwork `cover`, `back-cover`, or `ad-…` to assign its role during import. Use **Edit artwork…** to change it later.

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

Back up the entire **Goosnav Zine** folder to preserve the editable issue. Open this folder directly to resume a moved issue. Originals are read-only inputs. Processing and export work offline after setup. Close the terminal or press Ctrl+C to stop the editor.

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
