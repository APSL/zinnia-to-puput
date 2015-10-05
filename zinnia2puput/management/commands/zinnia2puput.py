# -*- coding: utf-8 -*-
import os
import lxml.html

from django.core.management import BaseCommand
from django.conf import settings
from django.core.files import File
from wagtail.wagtailcore.models import Page, Site
from wagtail.wagtailimages.models import Image as WagtailImage
from zinnia.models import Category as ZinniaCategory, Entry as ZinniaEntry


from puput.models import BlogPage, EntryPage, TagEntryPage as PuputTagEntryPage, Tag as PuputTag, \
    Category as PuputCategory, CategoryEntryPage as PuputCategoryEntryPage, EntryPageRelated


class Command(BaseCommand):
    help = "Import blog data from Zinnia"
    entries = {}

    def add_arguments(self, parser):
        parser.add_argument('--slug', default='blog', help="Slug of the blog.")
        parser.add_argument('--title', default='Blog', help="Title of the blog.")

    def handle(self, *args, **options):
        self.get_blog_page(options['slug'], options['title'])
        self.import_categories()
        self.import_entries()
        self.import_related_entries()

    def get_blog_page(self, slug, title):
        # Create blog page
        try:
            self.blogpage = BlogPage.objects.get(slug=slug)
        except BlogPage.DoesNotExist:
            # Get root page
            rootpage = Page.objects.first()

            # Set site root page as root site page
            site = Site.objects.first()
            site.root_page = rootpage
            site.save()

            # Get blogpage content type
            self.blogpage = BlogPage(
                title=title,
                slug=slug,
            )
            rootpage.add_child(instance=self.blogpage)
            revision = rootpage.save_revision()
            revision.publish()

    def import_categories(self):
        self.stdout.write("Importing categories...")
        categories = ZinniaCategory.objects.all()
        for category in categories:
            self.stdout.write("\t{}".format(category))
            puput_category, created = PuputCategory.objects.update_or_create(
                name=category.title,
                slug=category.slug,
                description=category.description
            )
            puput_category.save()

    def import_entries(self):
        self.stdout.write("Importing entries...")
        entries = ZinniaEntry.objects.all()
        for entry in entries:
            self.stdout.write(entry.title)
            # Header images
            if entry.image:
                header_image = WagtailImage(file=entry.image, title=os.path.basename(entry.image.url))
                self.stdout.write('\tImported header image: {}'.format(entry.image))
                header_image.save()
            else:
                header_image = None

            self.stdout.write('\tGenerate and replace entry content images....')
            if entry.content:
                root = lxml.html.fromstring(entry.content)
                for el in root.iter('img'):
                    if el.attrib['src'].startswith(settings.MEDIA_URL):
                        old_image = el.attrib['src'].replace(settings.MEDIA_URL, '')
                        with open('{}/{}'.format(settings.MEDIA_ROOT, old_image), 'r') as image_file:
                            new_image = WagtailImage(file=File(file=image_file, name=os.path.basename(old_image)),
                                                     title=os.path.basename(old_image))
                            new_image.save()
                            el.attrib['src'] = new_image.file.url
                            self.stdout.write('\t\t{}'.format(new_image.file.url))

                # New content with images replaced
                content = lxml.html.tostring(root, pretty_print=True)
            else:
                content = entry.content

            # Create page
            try:
                page = EntryPage.objects.get(slug=entry.slug)
            except EntryPage.DoesNotExist:
                page = EntryPage(
                    title=entry.title,
                    body=content,
                    slug=entry.slug,
                    go_live_at=entry.start_publication,
                    expire_at=entry.end_publication,
                    first_published_at=entry.creation_date,
                    date=entry.creation_date,
                    owner=entry.authors.first(),
                    seo_title=entry.title,
                    search_description=entry.excerpt,
                    live=entry.is_visible,
                    header_image=header_image
                )
                self.blogpage.add_child(instance=page)
                revision = self.blogpage.save_revision()
                revision.publish()
            self.import_entry_categories(entry, page)
            self.import_entry_tags(entry, page)
            page.save()
            page.save_revision(changed=False)
            self.entries[entry.pk] = page

    def import_related_entries(self):
        self.stdout.write("Importing related entries...")
        entries = ZinniaEntry.objects.all()
        for entry in entries:
            for related_entry in entry.related.all():
                EntryPageRelated.objects.get_or_create(entrypage_from=self.entries[entry.pk],
                                                       entrypage_to=self.entries[related_entry.pk])

    def import_entry_categories(self, entry, page):
        self.stdout.write("\tImporting categories...")
        for category in entry.categories.all():
            self.stdout.write('\t\tAdd category: {}'.format(category.title))
            puput_category = PuputCategory.objects.get(name=category.title)
            PuputCategoryEntryPage.objects.get_or_create(category=puput_category, page=page)

    def import_entry_tags(self, entry, page):
        self.stdout.write("\tImporting tags...")
        for tag in entry.tags_list:
            self.stdout.write('\t\t{}'.format(tag))
            puput_tag, created = PuputTag.objects.update_or_create(name=tag)
            page.entry_tags.add(PuputTagEntryPage(tag=puput_tag))
