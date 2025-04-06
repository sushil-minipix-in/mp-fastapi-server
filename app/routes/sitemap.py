import xml.etree.ElementTree as ET

from app.db import Mongo
from datetime import date, timedelta
from fastapi import APIRouter, Response

db = Mongo()
movies_collection = db.movies
series_collection = db.series
songs_collection = db.songs
domain = "https://minipix.in"

router = APIRouter()


@router.get("/index.xml")
async def sitemap_index():
    sitemapindex = ET.Element("sitemapindex")
    sitemapindex.set("xmlns", "https://www.sitemaps.org/schemas/sitemap/0.9")
    sitemap1 = ET.SubElement(sitemapindex, "sitemap")
    loc1 = ET.SubElement(sitemap1, "loc")
    loc1.text = f"{domain}/sitemap/movies.xml"
    lastmod1 = ET.SubElement(sitemap1, "lastmod")
    lastmod1.text = str(date.today() + timedelta(days=-1))
    sitemap2 = ET.SubElement(sitemapindex, "sitemap")
    loc2 = ET.SubElement(sitemap2, "loc")
    loc2.text = f"{domain}/sitemap/series.xml"
    lastmod2 = ET.SubElement(sitemap2, "lastmod")
    lastmod2.text = str(date.today() + timedelta(days=-1))
    return Response(content=ET.tostring(sitemapindex), media_type="application/xml")


@router.get("/movies.xml")
async def sitemap_movies():
    xmlversion = {'xmlns': "https://www.sitemaps.org/schemas/sitemap/0.9"}
    root = ET.Element('urlset', xmlversion)
    async for mov in movies_collection.find({}, {'slug': 1, 'title': 1, 'lastmod': 1}):
        mov['_id'] = str(mov['_id'])
        slug_url = f"movies/{mov.get('slug','movie')}-{mov['_id']}"
        node = ET.SubElement(root, 'url')
        loc = ET.SubElement(node, 'loc')
        loc.text = f"{domain}/{slug_url}"
        lastmod = ET.SubElement(node, 'lastmod')
        lastmod.text = mov.get('lastmod', date.today().isoformat())
    return Response(content=ET.tostring(root), media_type="application/xml")


@router.get("/series.xml")
async def sitemap_series():
    xmlversion = {'xmlns': "https://www.sitemaps.org/schemas/sitemap/0.9"}
    root = ET.Element('urlset', xmlversion)
    async for doc in series_collection.find({}, {'slug': 1, 'title': 1, 'lastmod': 1}):
        doc['_id'] = str(doc['_id'])
        slug_url = f"series/{doc.get('slug','series')}-{doc['_id']}"
        node = ET.SubElement(root, 'url')
        loc = ET.SubElement(node, 'loc')
        loc.text = f"{domain}/{slug_url}"
        lastmod = ET.SubElement(node, 'lastmod')
        lastmod.text = doc.get('lastmod', date.today().isoformat())
    return Response(content=ET.tostring(root), media_type="application/xml")
