import hashlib
import os
from collections import defaultdict

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from dashboard.models import DSRS, DSRSImage

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


def sha256_of(fh):
    h = hashlib.sha256()
    for chunk in iter(lambda: fh.read(1 << 20), b""):
        h.update(chunk)
    return h.hexdigest()


class Command(BaseCommand):
    help = "Import DSRS photos from folders named after the DSRS Location."

    def add_arguments(self, parser):
        parser.add_argument("root", help="Top folder to search (any depth)")
        parser.add_argument("--dry-run", action="store_true",
                            help="Report what would be imported, change nothing")

    def handle(self, *args, **opts):
        root, dry = opts["root"], opts["dry_run"]
        if not os.path.isdir(root):
            raise CommandError(f"Not a folder: {root}")

        # 1) index every folder in the tree by (lower-cased) name
        folders = defaultdict(list)
        for dirpath, _dirs, _files in os.walk(root):
            folders[os.path.basename(dirpath).strip().lower()].append(dirpath)

        # 2) group DSRS by location
        by_location = defaultdict(list)
        for d in DSRS.objects.exclude(Location__isnull=True).exclude(Location=""):
            by_location[d.Location.strip().lower()].append(d)

        added = skipped_dup = 0
        no_folder, ambiguous, no_images = [], [], []

        for loc, sources in sorted(by_location.items()):
            paths = folders.get(loc, [])
            if not paths:
                no_folder.append(loc)
                continue
            if len(paths) > 1:
                ambiguous.append((loc, paths))
                continue

            folder = paths[0]
            images = sorted(
                os.path.join(folder, f) for f in os.listdir(folder)
                if os.path.splitext(f)[1].lower() in IMAGE_EXT
                and os.path.isfile(os.path.join(folder, f))
            )
            if not images:
                no_images.append(loc)
                continue

            # existing content hashes per DSRS, so re-runs don't duplicate
            existing = {}
            for s in sources:
                hashes = set()
                for img in s.dsrs_images.all():
                    if not img.file:
                        continue
                    try:
                        with img.file.open("rb") as fh:
                            hashes.add(sha256_of(fh))
                    except (OSError, ValueError):
                        continue
                existing[s.pk] = hashes

            for path in images:
                with open(path, "rb") as fh:
                    digest = sha256_of(fh)

                stored_name = None
                for s in sources:
                    if digest in existing[s.pk]:
                        skipped_dup += 1
                        continue
                    added += 1
                    existing[s.pk].add(digest)
                    if dry:
                        continue
                    if stored_name is None:
                        obj = DSRSImage(dsrs=s)
                        with open(path, "rb") as fh:
                            obj.file.save(os.path.basename(path), File(fh), save=True)
                        stored_name = obj.file.name
                    else:
                        # same photo for another DSRS at this location: reuse the stored file
                        DSRSImage.objects.create(dsrs=s, file=stored_name)

        verb = "Would add" if dry else "Added"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {added} photo(s); {skipped_dup} already present."))
        if no_folder:
            self.stdout.write(f"{len(no_folder)} location(s) with no folder: "
                              + ", ".join(no_folder[:20]) + (" ..." if len(no_folder) > 20 else ""))
        if no_images:
            self.stdout.write(f"{len(no_images)} folder(s) with no images: "
                              + ", ".join(no_images[:20]))
        for loc, paths in ambiguous:
            self.stdout.write(self.style.WARNING(f"Ambiguous '{loc}' (skipped):"))
            for p in paths:
                self.stdout.write(f"    {p}")