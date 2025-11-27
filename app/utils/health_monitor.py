import asyncio
import aiosqlite
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from app.database.operations import DatabaseOperations
from app.client.session_manager import session_manager
from app.utils.logger import external_logger
from config import Config

class HealthMonitor:
    def __init__(self):
        self.db = DatabaseOperations()
        self.health_cache: Dict[int, dict] = {}
        self.monitoring_active = False
        self.last_check_time = datetime.now()
        
    async def start_monitoring(self):
        """Start continuous health monitoring"""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        await external_logger.send_log(
            0,  # System log
            "system",
            "Health monitoring started",
            "info"
        )
        
        # Start monitoring loop
        asyncio.create_task(self._monitoring_loop())
    
    async def stop_monitoring(self):
        """Stop health monitoring"""
        self.monitoring_active = False
        await external_logger.send_log(
            0,
            "system", 
            "Health monitoring stopped",
            "info"
        )
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.monitoring_active:
            try:
                await self._check_all_accounts_health()
                await asyncio.sleep(30)  # Check every 30 seconds
            except Exception as e:
                await external_logger.send_log(
                    0,
                    "system",
                    f"Health monitoring error: {str(e)}",
                    "error"
                )
                await asyncio.sleep(60)  # Wait longer on error
    
    async def _check_all_accounts_health(self):
        """Check health of all active accounts"""
        try:
            accounts = await self.db.get_all_accounts()
            current_time = datetime.now()
            
            for account in accounts:
                if not account['is_active']:
                    continue
                
                account_id = account['id']
                health_status = await self._check_account_health(account_id, account)
                
                # Update health cache
                self.health_cache[account_id] = {
                    'last_check': current_time,
                    'status': health_status,
                    'account_info': account
                }
                
                # Handle unhealthy accounts
                if health_status['health'] != 'healthy':
                    await self._handle_unhealthy_account(account_id, health_status)
                
                # Log health status periodically
                if (current_time - self.last_check_time).seconds >= 300:  # Every 5 minutes
                    await self._log_health_status(account_id, health_status)
            
            # Update last check time
            if (current_time - self.last_check_time).seconds >= 300:
                self.last_check_time = current_time
                
        except Exception as e:
            await external_logger.send_log(
                0,
                "system",
                f"Error checking accounts health: {str(e)}",
                "error"
            )
    
    async def _check_account_health(self, account_id: int, account: dict) -> dict:
        """Check individual account health"""
        health_status = {
            'health': 'healthy',
            'issues': [],
            'checks': {}
        }
        
        # Check 1: Client connection status
        client = session_manager.get_client(account_id)
        if client:
            try:
                if not client.is_connected():
                    health_status['issues'].append('client_disconnected')
                    health_status['health'] = 'unhealthy'
                health_status['checks']['client_connected'] = client.is_connected()
                
                # Check authorization
                if client.is_connected():
                    is_authorized = await client.is_user_authorized()
                    if not is_authorized:
                        health_status['issues'].append('session_expired')
                        health_status['health'] = 'critical'
                    health_status['checks']['authorized'] = is_authorized
                    
            except Exception as e:
                health_status['issues'].append(f'client_error: {str(e)}')
                health_status['health'] = 'critical'
                health_status['checks']['client_error'] = str(e)
        else:
            health_status['issues'].append('no_client')
            health_status['health'] = 'warning'
            health_status['checks']['client_loaded'] = False
        
        # Check 2: Broadcast status consistency
        try:
            is_broadcasting_db = account.get('is_broadcasting', False)
            is_broadcasting_memory = account_id in broadcast_worker.running_tasks
            
            health_status['checks']['broadcast_db'] = is_broadcasting_db
            health_status['checks']['broadcast_memory'] = is_broadcasting_memory
            
            # Inconsistency detected
            if is_broadcasting_db != is_broadcasting_memory:
                health_status['issues'].append('broadcast_status_inconsistent')
                if health_status['health'] == 'healthy':
                    health_status['health'] = 'warning'
                
                # Auto-fix inconsistency
                await self._fix_broadcast_inconsistency(account_id, is_broadcasting_db, is_broadcasting_memory)
                
        except Exception as e:
            health_status['checks']['broadcast_check_error'] = str(e)
        
        # Check 3: Recent activity
        try:
            recent_logs = await self.db.get_recent_logs(account_id, hours=1)
            health_status['checks']['recent_logs'] = len(recent_logs)
            
            # Check if account is broadcasting but has no recent logs
            if account.get('is_broadcasting', False) and len(recent_logs) == 0:
                health_status['issues'].append('broadcast_no_activity')
                health_status['health'] = 'critical'
                
        except Exception as e:
            health_status['checks']['activity_check_error'] = str(e)
        
        # Check 4: Last message time
        try:
            last_message_time = await self._get_last_message_time(account_id)
            if last_message_time:
                time_since_last = datetime.now() - last_message_time
                health_status['checks']['last_message_minutes'] = time_since_last.total_seconds() / 60
                
                # If broadcasting and no messages for too long
                if account.get('is_broadcasting', False) and time_since_last > timedelta(hours=2):
                    health_status['issues'].append('broadcast_stalled')
                    health_status['health'] = 'critical'
            else:
                health_status['checks']['last_message_minutes'] = None
                
        except Exception as e:
            health_status['checks']['message_time_check_error'] = str(e)
        
        # Check 5: Session age
        try:
            session_age = datetime.now() - datetime.fromisoformat(account['created_at'].replace('Z', '+00:00'))
            health_status['checks']['session_age_days'] = session_age.days
            
            # Very old sessions might need refresh
            if session_age.days > 30:
                health_status['issues'].append('old_session')
                if health_status['health'] == 'healthy':
                    health_status['health'] = 'warning'
                    
        except Exception as e:
            health_status['checks']['session_age_error'] = str(e)
        
        return health_status
    
    async def _fix_broadcast_inconsistency(self, account_id: int, db_status: bool, memory_status: bool):
        """Fix broadcast status inconsistency"""
        try:
            # Import here to avoid circular import
            from app.client.broadcast_worker import broadcast_worker
            
            if db_status and not memory_status:
                # DB says broadcasting but no task running - reset DB
                await self.db.update_account_broadcast_status(account_id, False)
                await self.db.add_log(
                    account_id,
                    "health_monitor",
                    "Fixed broadcast inconsistency: cleared stale DB status",
                    "info"
                )
                
            elif not db_status and memory_status:
                # Memory has task but DB says not broadcasting - stop task
                await broadcast_worker.stop_broadcast(account_id)
                await self.db.add_log(
                    account_id,
                    "health_monitor", 
                    "Fixed broadcast inconsistency: stopped orphaned task",
                    "info"
                )
                
        except Exception as e:
            await self.db.add_log(
                account_id,
                "health_monitor",
                f"Failed to fix broadcast inconsistency: {str(e)}",
                "error"
            )
    
    async def _handle_unhealthy_account(self, account_id: int, health_status: dict):
        """Handle unhealthy account based on severity"""
        issues = health_status['issues']
        health = health_status['health']
        
        # Critical issues - immediate action
        if health == 'critical':
            if 'session_expired' in issues:
                await self._handle_session_expired(account_id)
            elif 'broadcast_stalled' in issues:
                await self._handle_stalled_broadcast(account_id)
            elif 'broadcast_no_activity' in issues:
                await self._handle_inactive_broadcast(account_id)
        
        # Warning level - log and monitor
        elif health == 'warning':
            if 'old_session' in issues:
                await self.db.add_log(
                    account_id,
                    "health_monitor",
                    "Session is getting old, consider refreshing",
                    "warning"
                )
            elif 'broadcast_status_inconsistent' in issues:
                await self.db.add_log(
                    account_id,
                    "health_monitor",
                    "Broadcast status inconsistency detected and fixed",
                    "warning"
                )
    
    async def _handle_session_expired(self, account_id: int):
        """Handle expired session"""
        try:
            # Stop any running broadcasts
            await broadcast_worker.stop_broadcast(account_id)
            
            # Mark account as inactive
            await self.db.update_account_status(account_id, False)
            
            # Log the issue
            await self.db.add_log(
                account_id,
                "health_monitor",
                "Session expired - account deactivated. Please re-login.",
                "critical"
            )
            
            await external_logger.send_log(
                0,
                "system",
                f"Account {account_id} session expired - deactivated",
                "critical"
            )
            
        except Exception as e:
            await self.db.add_log(
                account_id,
                "health_monitor",
                f"Error handling expired session: {str(e)}",
                "error"
            )
    
    async def _handle_stalled_broadcast(self, account_id: int):
        """Handle stalled broadcast"""
        try:
            # Import here to avoid circular import
            from app.client.broadcast_worker import broadcast_worker
            
            # Restart the broadcast
            success, message = await broadcast_worker.start_broadcast(account_id)
            
            if success:
                await self.db.add_log(
                    account_id,
                    "health_monitor",
                    "Stalled broadcast detected and restarted",
                    "info"
                )
            else:
                await self.db.add_log(
                    account_id,
                    "health_monitor",
                    f"Failed to restart stalled broadcast: {message}",
                    "error"
                )
                # Stop the broken broadcast
                await broadcast_worker.stop_broadcast(account_id)
                
        except Exception as e:
            await self.db.add_log(
                account_id,
                "health_monitor",
                f"Error handling stalled broadcast: {str(e)}",
                "error"
            )
    
    async def _handle_inactive_broadcast(self, account_id: int):
        """Handle broadcast with no activity"""
        try:
            # Import here to avoid circular import
            from app.client.broadcast_worker import broadcast_worker
            
            # Check if broadcast task is actually running
            if account_id in broadcast_worker.running_tasks:
                # Task exists but no logs - might be frozen
                await broadcast_worker.stop_broadcast(account_id)
                await self.db.add_log(
                    account_id,
                    "health_monitor",
                    "Frozen broadcast detected and stopped",
                    "warning"
                )
                
                # Try to restart
                await asyncio.sleep(5)
                success, message = await broadcast_worker.start_broadcast(account_id)
                
                if success:
                    await self.db.add_log(
                        account_id,
                        "health_monitor",
                        "Broadcast restarted successfully",
                        "info"
                    )
                else:
                    await self.db.add_log(
                        account_id,
                        "health_monitor",
                        f"Failed to restart broadcast: {message}",
                        "error"
                    )
            else:
                # No task but DB shows broadcasting - fix inconsistency
                await self.db.update_account_broadcast_status(account_id, False)
                await self.db.add_log(
                    account_id,
                    "health_monitor",
                    "Cleared stale broadcast status (no activity)",
                    "info"
                )
                
        except Exception as e:
            await self.db.add_log(
                account_id,
                "health_monitor",
                f"Error handling inactive broadcast: {str(e)}",
                "error"
            )
    
    async def _get_last_message_time(self, account_id: int) -> Optional[datetime]:
        """Get timestamp of last sent message"""
        try:
            async with aiosqlite.connect(self.db.db_path) as db:
                cursor = await db.execute(
                    "SELECT MAX(last_message_sent) FROM groups WHERE account_id = ? AND last_message_sent IS NOT NULL",
                    (account_id,)
                )
                result = await cursor.fetchone()
                if result and result[0]:
                    return datetime.fromisoformat(result[0].replace('Z', '+00:00'))
        except:
            pass
        return None
    
    async def _log_health_status(self, account_id: int, health_status: dict):
        """Log periodic health status"""
        health = health_status['health']
        issues_count = len(health_status['issues'])
        
        if health == 'healthy':
            status_msg = f"Account health: {health} ✅"
        else:
            status_msg = f"Account health: {health} ⚠️ ({issues_count} issues: {', '.join(health_status['issues'])})"
        
        await self.db.add_log(
            account_id,
            "health_monitor",
            status_msg,
            "info" if health == 'healthy' else "warning"
        )
    
    async def get_health_summary(self) -> dict:
        """Get overall health summary of all accounts"""
        try:
            accounts = await self.db.get_all_accounts()
            summary = {
                'total_accounts': len(accounts),
                'healthy': 0,
                'warning': 0,
                'critical': 0,
                'inactive': 0,
                'details': []
            }
            
            for account in accounts:
                if not account['is_active']:
                    summary['inactive'] += 1
                    continue
                
                account_id = account['id']
                if account_id in self.health_cache:
                    health_data = self.health_cache[account_id]
                    health = health_data['status']['health']
                    summary[health] += 1
                    
                    summary['details'].append({
                        'account_id': account_id,
                        'phone': account['phone_number'],
                        'health': health,
                        'issues': health_data['status']['issues'],
                        'last_check': health_data['last_check'].isoformat()
                    })
                else:
                    summary['warning'] += 1  # Unknown status
            
            return summary
            
        except Exception as e:
            return {
                'error': str(e),
                'total_accounts': 0,
                'healthy': 0,
                'warning': 0,
                'critical': 0,
                'inactive': 0,
                'details': []
            }
    
    async def force_health_check(self, account_id: int = None) -> dict:
        """Force immediate health check for specific account or all accounts"""
        if account_id:
            account = await self.db.get_account(account_id)
            if account:
                health_status = await self._check_account_health(account_id, account)
                self.health_cache[account_id] = {
                    'last_check': datetime.now(),
                    'status': health_status,
                    'account_info': account
                }
                return {account_id: health_status}
        else:
            await self._check_all_accounts_health()
            return self.health_cache

# Global instance
health_monitor = HealthMonitor()
