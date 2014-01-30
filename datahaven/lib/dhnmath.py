#!/usr/bin/python
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
import time
import datetime

#-------------------------------------------------------------------------------

def interval_to_next_hour():
    _struct_time = list(time.localtime())
    _struct_time[4] = 0
    _struct_time[5] = 0
    prev_hour_time = time.mktime(_struct_time)
    return prev_hour_time + 60*60 - time.time()

#-------------------------------------------------------------------------------

def shedule_continuously(last_time, interval):
    try:
        dt = time.time() - float(last_time)
        n = int(dt / float(interval))
    except:
        return None
    return float(last_time) + (n+1)*float(interval)

#-------------------------------------------------------------------------------

def shedule_next_hourly(last_time, interval):
    try:
        t = list(time.localtime(float(last_time)))
        t[4] = 0
        t[5] = 0
        while True:
            t[3] += int(interval)
            tm = time.mktime(t)
            if tm > time.time():
                return tm
    except:
        pass
    return None

#------------------------------------------------------------------------------

def shedule_next_daily(last_time, period_string, start_time_string):
    try:
        start_time_structtime = list(time.strptime(start_time_string, '%H:%M:%S'))
    except:
        try:
            start_time_structtime = list(time.strptime(start_time_string, '%H:%M'))
        except:
            import dhnio
            dhnio.DprintException()
            return None
    try:
        last_datetime = datetime.datetime.fromtimestamp(float(last_time))
        period = int(period_string)
    except:
        print 'DEBUG: next_daily1'
        import dhnio
        dhnio.DprintException()
        return None
    if period == 0:
        print 'DEBUG: next_daily2'
        return None

    start_time = datetime.time(
        hour = start_time_structtime[3], 
        minute = start_time_structtime[4], 
        second = start_time_structtime[5])

    today = datetime.datetime.today()
    time_ok = today.time() < start_time
    day_offset = today.toordinal() - last_datetime.toordinal()
    period_ok = day_offset % period == 0

    if time_ok and period_ok:
        today = today.replace(
            hour = start_time.hour, 
            minute = start_time.minute, 
            second = start_time.second, 
            microsecond = 0)
        return time.mktime(today.timetuple())

    today = today.replace(
        hour = start_time.hour, 
        minute = start_time.minute, 
        second = start_time.second, 
        microsecond = 0)
    delta_days = period - day_offset
    while delta_days < 0:
        delta_days += 365
    today = today + datetime.timedelta(days = delta_days)
    return time.mktime(today.timetuple())

#------------------------------------------------------------------------------ 

def shedule_next_weekly(last_time, period_string, start_time_string, week_days):
    try:
        start_time_structtime = list(time.strptime(start_time_string, '%H:%M:%S'))
    except:
        try:
            start_time_structtime = list(time.strptime(start_time_string, '%H:%M'))
        except:
            import dhnio
            dhnio.DprintException()
            return None
    try:
        last_datetime = datetime.datetime.fromtimestamp(float(last_time))
        period = int(period_string)
    except:
        import dhnio
        dhnio.DprintException()
        return None
    if len(week_days) == 0 or period == 0:
        print 'DEBUG: next_weekly2'
        return None

    start_time = datetime.time(
        hour = start_time_structtime[3], 
        minute = start_time_structtime[4],
        second = start_time_structtime[5])

    today = datetime.datetime.today()

    week_ok = today.weekday() in week_days
    time_ok = today.time() < start_time

    last_iso_year, last_iso_week, last_iso_weekday = last_datetime.isocalendar()
    today_iso_year, today_iso_week, today_iso_weekday = today.isocalendar()
    period_ok = (today_iso_week - last_iso_week) % period == 0

    if time_ok and week_ok and period_ok:
        today = today.replace(
            hour = start_time.hour, 
            minute = start_time.minute, 
            second = start_time.second, 
            microsecond = 0)
        return time.mktime(today.timetuple())

    today = today.replace(hour=0, minute=0, second=0, microsecond=0)

    while True:
        today = today + datetime.timedelta(days=1)
        week_ok = today.weekday() in week_days

        today_iso_year, today_iso_week, today_iso_weekday = today.isocalendar()
        period_ok = (today_iso_week - last_iso_week) % period == 0

        if week_ok and period_ok:
            break

    today = today.replace(
        hour = start_time.hour, 
        minute = start_time.minute, 
        second = start_time.second, 
        microsecond = 0)
    return time.mktime(today.timetuple())

#------------------------------------------------------------------------------ 

def shedule_next_monthly_old(last_time, day_string, start_time_string, months):
    try:
        start_time_structtime = list(time.strptime(start_time_string, '%H:%M:%S'))
    except:
        try:
            start_time_structtime = list(time.strptime(start_time_string, '%H:%M'))
        except:
            import dhnio
            dhnio.DprintException()
            return None
    try:
        last_datetime = datetime.datetime.fromtimestamp(float(last_time))
        day = int(day_string)
    except:
        import dhnio
        dhnio.DprintException()
        return None
    if len(months) == 0 or day > 31 or day < 1:
        print 'DEBUG: next_monthly2'
        return None

    start_time = datetime.time(
        hour = start_time_structtime[3], 
        minute = start_time_structtime[4],
        second = start_time_structtime[5])

    today = datetime.datetime.today()

    month_ok = today.month in months
    day_ok = today.day == day
    time_ok = today.time() < start_time

    if month_ok and day_ok and time_ok:
        today = today.replace(
            hour = start_time.hour, 
            minute = start_time.minute, 
            second = start_time.second, 
            microsecond = 0)
        return time.mktime(today.timetuple())

    today = today.replace(hour=0, minute=0, second=0, microsecond=0)

    month = today.month
    if today.day > day or not time_ok:
        month = month + 1
    today = today.replace(day=day)

    while True:
        if month > 12:
            month = 1
            today = today.replace(year=today.year+1)
        today = today.replace(month=month)
        if month in months:
            break

        month += 1

    today = today.replace(
        hour = start_time.hour, 
        minute = start_time.minute, 
        second = start_time.second, 
        microsecond = 0)
    return time.mktime(today.timetuple())

#------------------------------------------------------------------------------ 

def shedule_next_monthly(last_time, interval_months_string, start_time_string, dates):
    try:
        start_time_structtime = list(time.strptime(start_time_string, '%H:%M:%S'))
    except:
        try:
            start_time_structtime = list(time.strptime(start_time_string, '%H:%M'))
        except:
            import dhnio
            dhnio.DprintException()
            return None
    try:
        last_datetime = datetime.datetime.fromtimestamp(float(last_time))
        interval_months = int(interval_months_string)
    except:
        import dhnio
        dhnio.DprintException()
        return None

    good_dates = []
    for d in dates:
        try:
            int(d)
        except:
            continue
        good_dates.append(int(d))
            
    if len(good_dates) == 0:
        good_dates.append(1)
    
    dates = good_dates

    months = []
    for month in range(12):
        if month % interval_months == 0:
            months.append(month + 1)
            
    if len(months) == 0:
        months.append(1)
        
    start_time = datetime.time(
        hour = start_time_structtime[3], 
        minute = start_time_structtime[4],
        second = start_time_structtime[5])

    today = datetime.datetime.today()
    
    day_ok = today.day in dates
    time_ok = today.time() < start_time
    month_ok = today.month in months

    if month_ok and day_ok and time_ok:
        del months 
        today = today.replace(
            hour = start_time.hour, 
            minute = start_time.minute, 
            second = start_time.second, 
            microsecond = 0)
        return time.mktime(today.timetuple())

    day = today.day
    month = today.month

    if not time_ok:
        day += 1
        #today = today.replace(hour=0, minute=0, second=0, microsecond=0)

    if not day in dates:
        while True:
            day += 1
            if day > 31:
                day = 1
                month += 1
                if month > 12:
                    month = 1
            if month in months and day in dates:
                break

    del months
    today = today.replace(
        month = month, 
        day = day,
        hour = start_time.hour, 
        minute = start_time.minute, 
        second = start_time.second, 
        microsecond = 0)
    return time.mktime(today.timetuple())

#-------------------------------------------------------------------------------

def toInt(s, default=0):
    try:
        return int(s)
    except:
        return default

def toFloat(s, default=0.0):
    try:
        return float(s)
    except:
        return default

#------------------------------------------------------------------------------ 

#tests
if __name__ == '__main__':

#    print interval_to_next_hour()
#    t = 1286897649.59
##    print time.asctime(time.localtime(shedule_non_stop(t, 60*60)))
##    print shedule_non_stop(t, 60*60) - time.time()
#    print shedule_next_hourly(time.time()-60*60*9-12, 1)/60
    t = shedule_next_monthly(time.time()-60*60*9-12, '1', '14:00', ['2','6','9', '15', '16'])
    print time.time(), t , time.time() - t
    print time.asctime(time.localtime(t))
    print time.asctime(time.localtime())
