from mwclient import Site
from SiteCookie import CookieGetter
from bs4 import BeautifulSoup
import imageio.v3 as iio
import requests
import pandoc
import re

bsite = Site("wiki.biligame.com/sbox", path="/", scheme="https")
bsite.login(cookies = CookieGetter.get("Edge")) # I am using Edge in this case

CACHE_FOLDER = "__pycache__/"
FP_WIKI_URL = "https://wiki.facepunch.com/sbox/" # FP's proprietary wiki
FP_WIKI_FILES_URL = "https://files.facepunch.com/wiki/files/"
FP_WIKI_SOUP = BeautifulSoup(requests.get(FP_WIKI_URL).text, "html.parser")
BWIKI_SUPPORTED_MEDIA_FORMATS = {"jpg" : True, "png" : True, "gif" : True}

#   Header
#       Category
#           Choice @ relativePath

def getSideBarHeaderCategories():
    elements = FP_WIKI_SOUP.find_all("span", class_ = "child-count")

    return [span.previous_element for span in elements], [int(span.contents[0]) for span in elements]

def getSideBarHeaderCategoryCount():
    return [len(section.find_all("details", class_ = "level1")) for section in FP_WIKI_SOUP.select("body > #sidebar > div > #contents > .section")]

removeSboxPrefix = lambda markup:re.sub(r"^/?sbox/", "", markup, flags=re.I)

def getSideBarChoices():
    names = []
    relativePaths = []

    for href in FP_WIKI_SOUP.select("body > #sidebar > div > #contents > .section > details > ul > li"):
        for choice in href.find_all("a"):
            path = removeSboxPrefix(choice.get("href")) or "index.php" # avoid `/sbox/` => ``
            names.append(choice.contents[0])
            relativePaths.append(path)

    return names, relativePaths

FP_WIKI_SIDEBAR_CHOICES, FP_WIKI_SIDEBAR_PATHS = getSideBarChoices()

def buildMenuStructure():
    struct = []
    count = getSideBarHeaderCategoryCount()
    categories, subCount = getSideBarHeaderCategories()

    pastHeaders, pastCategories, pastChoices = 0, 0, 0

    for header in FP_WIKI_SOUP.find_all("div", class_ = "sectionheader"):
        name = header.contents[0]
        struct.append("\r=" + name + "=")

        for i in range(pastCategories, pastCategories + count[pastHeaders]):
            struct.append("\r*" + categories[i])

            for j in range(pastChoices, pastChoices + subCount[pastCategories]):
                struct.append("\r#[[" + FP_WIKI_SIDEBAR_PATHS[j] + "|" + FP_WIKI_SIDEBAR_CHOICES[j] + "]]")
                pastChoices += 1

            pastCategories += 1
        pastHeaders += 1

    return struct

def buildAllArticles(start, end):
    n = len(FP_WIKI_SIDEBAR_PATHS)

    def sanitiseFileName(name):
        return name.split('/')[-1].capitalize()

    def cleanUselessTags(markup, tag):
        TAG = f"<{tag}>[^/</>//]+</{tag}>"
        matches = re.search(TAG, markup, re.S)
        while matches:
            markup = markup.replace(matches.group(), "")
            matches = re.search(TAG, markup, re.S)
        return markup

    def getFileType(name):
        return name.split(".")[-1]

    def uploadMedia(url):
        fileName = sanitiseFileName(url)
        savePath = CACHE_FOLDER + fileName
        if getFileType(fileName) == "gif":
            with open(savePath, "wb") as file:
                file.write(requests.get(url).content)
        else:
            im = iio.imread(url)
            iio.imwrite(savePath, im)
        bsite.upload(open(savePath, mode="rb"), fileName)

    def sanitiseUploads(markup):
        TAG_UPLOAD = r"<upload.*?src=\"([^\"]*)\".*?size=\"([^\"]*).*?name=\"([^\"]*).*?>"
        TAG_UPLOAD_MD = r"\[\[File:(https[^\[\]]+)\]\]"
        matches = re.search(TAG_UPLOAD, markup)
        while matches:
            relativePath = matches.groups()[0]
            fullUrl = FP_WIKI_FILES_URL + relativePath
            ext = getFileType(relativePath)

            if ext in BWIKI_SUPPORTED_MEDIA_FORMATS:
                uploadMedia(fullUrl)
                markup = markup.replace(matches.group(), f"[[File:{sanitiseFileName(relativePath)}|thumb]]")
            else:
                markup = markup.replace(matches.group(), f"[{fullUrl} {relativePath}]")

            matches = re.search(TAG_UPLOAD, markup)

        matches = re.search(TAG_UPLOAD_MD, markup, re.S)
        while matches:
            path = matches.groups()[0]
            ext = getFileType(path)

            if ext in BWIKI_SUPPORTED_MEDIA_FORMATS:
                uploadMedia(path)
                markup = markup.replace(matches.group(), f"[[File:{sanitiseFileName(path)}|thumb]]")

            matches = re.search(TAG_UPLOAD_MD, markup, re.S)
        return markup

    sanitiseKeys = lambda markup:markup.replace("<key>", "<kbd>").replace("</key>", "</kbd>")

    def sanitiseOnce(markup):
        title = lambda markup:markup.replace("<title>", "{{DISPLAYTITLE:").replace("</title>", "}}")
        cat = lambda markup:markup.replace("<cat>", "[[Category:").replace("</cat>", "]]")
        return title(cat(markup))

    def sanitiseNotices(markup):
        notes = lambda text:text.replace("<note>", "{{提示|笔记|").replace("</note>", "|注意}}")
        warnings = lambda text:text.replace("<warning>", "{{提示|警告|").replace("</warning>", "|警告}}")
        return notes(warnings(markup))

    def sanitisePageLinks(markup):
        TAG_LINK = r"<page[\s*text=\"]*?([^\"]*?)[\"]*?>(.*?)</page>"
        matches = re.search(TAG_LINK, markup, re.S)

        while matches:
            text = matches.groups()[0]
            pageName = removeSboxPrefix(matches.groups()[1])

            if text:
                markup = markup.replace(matches.group(), f"[[{pageName}|{text}]]")
            else:
                markup = markup.replace(matches.group(), f"[[{pageName}]]")
            matches = re.search(TAG_LINK, markup, re.S)
        return markup

    sanitise = lambda markup:sanitisePageLinks(sanitiseOnce(sanitiseKeys(sanitiseNotices(sanitiseUploads(markup)))))

    for i in range(n):
        if i < start:
            continue
        if i > end:
            break
        path = FP_WIKI_SIDEBAR_PATHS[i]
        page = bsite.pages[path]

        src = pandoc.read(requests.get(FP_WIKI_URL + path + "?format=text").text, format="markdown")
        dest = pandoc.write(src, format="mediawiki", options=["-s"])

        cleanedTags = cleanUselessTags(cleanUselessTags(sanitise(dest), "title"), "cat")

        page.edit(cleanedTags)

def deleteAllPages():
    for page in bsite.pages:
        for path in FP_WIKI_SIDEBAR_PATHS:
            if path == page.name:
                page.delete()

#buildAllArticles(0, 15)
#deleteAllPages()

# TODO: automatically generate HEADER and FOOTER
def updateBWikiIndex(header, footer):
    menu = "".join(buildMenuStructure())
    index = bsite.pages["首页"]
    index.edit(header + menu + footer)

HEADER = ''''''
FOOTER = ''''''

#updateBWikiIndex(HEADER, FOOTER)