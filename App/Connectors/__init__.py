"""Registry of platform connectors. Register a new platform by adding its connector to ConnectorList."""
from .Base import Connector, ConnectorError, ChannelInfo, SourceItem, ContentItem
from .Substack import SubstackConnector
from .Website import WebsiteConnector
from .X import XConnector
from .YouTube import YouTubeConnector

# Order matters for auto-detection: the website connector accepts any address, so it comes last.
ConnectorList = [YouTubeConnector(), XConnector(), SubstackConnector(), WebsiteConnector()]


def ConnectorGet(Platform: int) -> Connector:
    for Item in ConnectorList:
        if Item.Platform == Platform:
            return Item
    raise ConnectorError('There is no connector for that platform yet.')


def ConnectorDetect(Input: str) -> Connector | None:
    """The connector whose platform the input unmistakably names, or None (e.g. a bare @handle)."""
    for Item in ConnectorList:
        if Item.InputMatch(Input):
            return Item
    return None
