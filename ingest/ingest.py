import schedule
import time

import condor
import hadoop
import transferstats
import status
import userprio

if __name__ == "__main__":

    schedule.every(10).minutes.do(status.run)
    schedule.every(60).minutes.do(hadoop.run)
    schedule.every(30).minutes.do(condor.run)
    schedule.every(10).minutes.do(userprio.run)

    # schedule.run_all()
    while True:
        schedule.run_pending()
        time.sleep(60)

