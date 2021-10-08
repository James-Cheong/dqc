import logging.handlers
from DQC.config import settings

logging.basicConfig(
    format='[ %(asctime)s - %(name)s - %(levelname)s ] %(message)s',
    level=settings.log_level, filename='log/dqc.log', filemode='w')

logger = logging.getLogger(__name__)

smtp_handler = logging.handlers.SMTPHandler(mailhost=(settings.email_host, 25),
                                            fromaddr='dqc@datasolutions',
                                            toaddrs=settings.email_receiver,
                                            subject=u'DQC error!')

logger.addHandler(smtp_handler)
