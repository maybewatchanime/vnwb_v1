#!/usr/bin/env python3
"""
Traffic Monitor for VPN Bot
Мониторинг трафика и статистики пользователей
"""

import json
import subprocess
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import asyncio
import aiofiles

class TrafficMonitor:
    def __init__(self, xray_config_path: str, database_path: str):
        self.xray_config = xray_config_path
        self.database_path = database_path
        
    async def get_xray_stats(self) -> Dict:
        """Получить статистику из Xray через API"""
        try:
            # Xray API обычно доступен на порту 10085
            cmd = ["curl", "-s", "http://127.0.0.1:10085/stats/query"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                return json.loads(result.stdout)
            return {}
        except:
            return {}
    
    async def parse_access_log(self, log_path: str = "/home/vpsadmin/xray_log/access.log") -> Dict:
        """Парсинг логов доступа Xray"""
        stats = {}
        
        try:
            async with aiofiles.open(log_path, 'r') as f:
                lines = await f.readlines()
                
            for line in lines[-10000:]:  # Последние 10000 строк
                # Парсим email и трафик из логов
                if "email:" in line:
                    match = re.search(r'email:\s*([^\s]+).*traffic:\s*(\d+)', line)
                    if match:
                        email = match.group(1)
                        traffic = int(match.group(2))
                        
                        if email not in stats:
                            stats[email] = {"upload": 0, "download": 0, "total": 0}
                        
                        stats[email]["total"] += traffic
                        
                # Парсим UUID и последнее подключение
                if "accepted" in line.lower():
                    match = re.search(r'([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})', line)
                    if match:
                        uuid = match.group(1)
                        timestamp_match = re.search(r'(\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})', line)
                        if timestamp_match:
                            timestamp = datetime.strptime(timestamp_match.group(1), "%Y/%m/%d %H:%M:%S")
                            if uuid not in stats:
                                stats[uuid] = {}
                            stats[uuid]["last_seen"] = timestamp.isoformat()
            
            return stats
        except Exception as e:
            print(f"Error parsing logs: {e}")
            return {}
    
    async def get_system_stats(self) -> Dict:
        """Получить системную статистику"""
        stats = {}
        
        try:
            # CPU usage
            cpu_cmd = ["top", "-bn1"]
            cpu_result = subprocess.run(cpu_cmd, capture_output=True, text=True)
            cpu_match = re.search(r'%Cpu\(s\):\s+(\d+\.\d+)', cpu_result.stdout)
            if cpu_match:
                stats["cpu_usage"] = float(cpu_match.group(1))
            
            # Memory usage
            mem_cmd = ["free", "-m"]
            mem_result = subprocess.run(mem_cmd, capture_output=True, text=True)
            lines = mem_result.stdout.split('\n')
            if len(lines) > 1:
                mem_parts = lines[1].split()
                if len(mem_parts) > 2:
                    total_mem = int(mem_parts[1])
                    used_mem = int(mem_parts[2])
                    stats["memory_usage"] = (used_mem / total_mem) * 100
                    stats["memory_total_mb"] = total_mem
                    stats["memory_used_mb"] = used_mem
            
            # Disk usage
            disk_cmd = ["df", "-h", "/"]
            disk_result = subprocess.run(disk_cmd, capture_output=True, text=True)
            lines = disk_result.stdout.split('\n')
            if len(lines) > 1:
                disk_parts = lines[1].split()
                if len(disk_parts) > 4:
                    stats["disk_usage"] = disk_parts[4].replace('%', '')
                    stats["disk_total"] = disk_parts[1]
                    stats["disk_used"] = disk_parts[2]
            
            # Network stats
            net_cmd = ["vnstat", "-d", "1", "--json"]
            net_result = subprocess.run(net_cmd, capture_output=True, text=True)
            if net_result.returncode == 0:
                net_data = json.loads(net_result.stdout)
                if "interfaces" in net_data and net_data["interfaces"]:
                    interface = net_data["interfaces"][0]
                    if "traffic" in interface:
                        today_traffic = interface["traffic"]["day"][-1] if interface["traffic"]["day"] else {}
                        stats["bandwidth_today_gb"] = {
                            "rx": today_traffic.get("rx", 0) / (1024**3),
                            "tx": today_traffic.get("tx", 0) / (1024**3)
                        }
            
            # Xray service status
            xray_cmd = ["systemctl", "is-active", "xray"]
            xray_result = subprocess.run(xray_cmd, capture_output=True, text=True)
            stats["xray_status"] = xray_result.stdout.strip() == "active"
            
            # Uptime
            uptime_cmd = ["uptime", "-p"]
            uptime_result = subprocess.run(uptime_cmd, capture_output=True, text=True)
            stats["uptime"] = uptime_result.stdout.strip()
            
        except Exception as e:
            print(f"Error getting system stats: {e}")
        
        return stats
    
    async def update_user_traffic(self) -> None:
        """Обновить статистику трафика пользователей в БД"""
        try:
            # Загружаем базу данных
            async with aiofiles.open(self.database_path, 'r') as f:
                content = await f.read()
                db = json.loads(content)
            
            # Получаем статистику из логов
            traffic_stats = await self.parse_access_log()
            
            # Обновляем данные пользователей
            for user_id, configs in db.get("configs", {}).items():
                for config in configs:
                    uuid = config.get("uuid")
                    if uuid and uuid in traffic_stats:
                        config["traffic_used"] = traffic_stats[uuid].get("total", 0)
                        config["last_seen"] = traffic_stats[uuid].get("last_seen")
            
            # Сохраняем обновленную БД
            async with aiofiles.open(self.database_path, 'w') as f:
                await f.write(json.dumps(db, indent=2, ensure_ascii=False))
            
        except Exception as e:
            print(f"Error updating user traffic: {e}")
    
    async def generate_report(self) -> str:
        """Генерация отчета о состоянии системы"""
        system_stats = await self.get_system_stats()
        traffic_stats = await self.parse_access_log()
        
        # Загружаем БД для подсчета пользователей
        try:
            async with aiofiles.open(self.database_path, 'r') as f:
                content = await f.read()
                db = json.loads(content)
        except:
            db = {"users": {}, "configs": {}}
        
        # Считаем активных пользователей (подключались в последние 24 часа)
        active_users = 0
        now = datetime.now()
        
        for user_id, configs in db.get("configs", {}).items():
            for config in configs:
                if config.get("last_seen"):
                    last_seen = datetime.fromisoformat(config["last_seen"])
                    if (now - last_seen).total_seconds() < 86400:  # 24 часа
                        active_users += 1
                        break
        
        report = f"""
📊 СИСТЕМНЫЙ ОТЧЕТ VPN СЕРВЕРА
═══════════════════════════════════

📅 Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

👥 ПОЛЬЗОВАТЕЛИ:
├─ Всего зарегистрировано: {len(db.get('users', {}))}
├─ Активных за 24ч: {active_users}
└─ Всего конфигураций: {sum(len(configs) for configs in db.get('configs', {}).values())}

💻 СИСТЕМА:
├─ CPU: {system_stats.get('cpu_usage', 'N/A')}%
├─ RAM: {system_stats.get('memory_used_mb', 0)}/{system_stats.get('memory_total_mb', 0)} MB ({system_stats.get('memory_usage', 0):.1f}%)
├─ Диск: {system_stats.get('disk_used', 'N/A')}/{system_stats.get('disk_total', 'N/A')} ({system_stats.get('disk_usage', 'N/A')}%)
└─ Uptime: {system_stats.get('uptime', 'N/A')}

🌐 ТРАФИК СЕГОДНЯ:
├─ Входящий: {system_stats.get('bandwidth_today_gb', {}).get('rx', 0):.2f} GB
└─ Исходящий: {system_stats.get('bandwidth_today_gb', {}).get('tx', 0):.2f} GB

🔧 СЕРВИСЫ:
├─ Xray: {'✅ Работает' if system_stats.get('xray_status') else '❌ Остановлен'}
└─ VPN Bot: {'✅ Работает' if await self.check_bot_status() else '❌ Остановлен'}

═══════════════════════════════════
"""
        
        return report
    
    async def check_bot_status(self) -> bool:
        """Проверить статус бота"""
        try:
            cmd = ["systemctl", "is-active", "vpn-bot"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.stdout.strip() == "active"
        except:
            return False
    
    async def cleanup_expired_users(self) -> int:
        """Очистка истекших подписок"""
        cleaned = 0
        
        try:
            # Загружаем конфигурацию Xray
            async with aiofiles.open(self.xray_config, 'r') as f:
                content = await f.read()
                xray_config = json.loads(content)
            
            # Загружаем БД
            async with aiofiles.open(self.database_path, 'r') as f:
                content = await f.read()
                db = json.loads(content)
            
            now = datetime.now()
            
            # Проверяем каждого пользователя
            for user_id, user_data in db.get("users", {}).items():
                if user_data.get("subscription_end"):
                    sub_end = datetime.fromisoformat(user_data["subscription_end"])
                    
                    # Если подписка истекла
                    if sub_end < now and user_data.get("is_active"):
                        user_data["is_active"] = False
                        
                        # Удаляем из Xray конфига
                        configs = db.get("configs", {}).get(user_id, [])
                        for config in configs:
                            uuid = config.get("uuid")
                            if uuid:
                                # Удаляем из inbounds
                                for inbound in xray_config.get("inbounds", []):
                                    if inbound.get("protocol") == "vless":
                                        clients = inbound.get("settings", {}).get("clients", [])
                                        inbound["settings"]["clients"] = [
                                            c for c in clients if c.get("id") != uuid
                                        ]
                                cleaned += 1
            
            # Сохраняем изменения
            if cleaned > 0:
                # Сохраняем Xray конфиг
                async with aiofiles.open(self.xray_config, 'w') as f:
                    await f.write(json.dumps(xray_config, indent=2, ensure_ascii=False))
                
                # Сохраняем БД
                async with aiofiles.open(self.database_path, 'w') as f:
                    await f.write(json.dumps(db, indent=2, ensure_ascii=False))
                
                # Перезапускаем Xray
                subprocess.run(["sudo", "systemctl", "restart", "xray"])
            
        except Exception as e:
            print(f"Error cleaning expired users: {e}")
        
        return cleaned

async def main():
    """Главная функция мониторинга"""
    monitor = TrafficMonitor(
        xray_config_path="/usr/local/etc/xray/config.json",
        database_path="/home/vpsadmin/vpn_bot/database.json"
    )
    
    print("🔄 Запуск мониторинга трафика VPN...")
    
    while True:
        try:
            # Обновляем статистику трафика
            await monitor.update_user_traffic()
            
            # Очищаем истекшие подписки
            cleaned = await monitor.cleanup_expired_users()
            if cleaned > 0:
                print(f"🧹 Очищено истекших подписок: {cleaned}")
            
            # Генерируем отчет каждые 6 часов
            current_hour = datetime.now().hour
            if current_hour % 6 == 0:
                report = await monitor.generate_report()
                print(report)
                
                # Сохраняем отчет в файл
                report_path = f"/home/vpsadmin/vpn_bot/logs/report_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
                async with aiofiles.open(report_path, 'w') as f:
                    await f.write(report)
            
            # Ждем 1 час перед следующей проверкой
            await asyncio.sleep(3600)
            
        except KeyboardInterrupt:
            print("\n⛔ Мониторинг остановлен")
            break
        except Exception as e:
            print(f"❌ Ошибка в мониторинге: {e}")
            await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
