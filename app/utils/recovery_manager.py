import asyncio
from app.utils.logger import external_logger

class RecoveryManager:
    def __init__(self):
        self.recovery_running = False
        
    async def start_recovery_service(self):
        """Start automatic recovery service"""
        if self.recovery_running:
            return
            
        self.recovery_running = True
        asyncio.create_task(self._recovery_loop())
        
    async def stop_recovery_service(self):
        """Stop automatic recovery service"""
        self.recovery_running = False
    
    async def _recovery_loop(self):
        """Main recovery loop"""
        while self.recovery_running:
            try:
                # Import here to avoid circular imports
                from app.utils.health_monitor import health_monitor
                from app.client.broadcast_worker import broadcast_worker
                
                # Check for frozen tasks
                await broadcast_worker.check_and_fix_frozen_tasks()
                
                # Get health summary
                health_summary = await health_monitor.get_health_summary()
                
                # Log critical issues
                critical_accounts = [acc for acc in health_summary.get('details', []) 
                                   if acc.get('health') == 'critical']
                
                if critical_accounts:
                    await external_logger.send_log(
                        0,
                        "recovery_service",
                        f"Found {len(critical_accounts)} critical accounts requiring attention",
                        "critical"
                    )
                
                # Wait before next check
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                await external_logger.send_log(
                    0,
                    "recovery_service",
                    f"Recovery service error: {str(e)}",
                    "error"
                )
                await asyncio.sleep(600)  # Wait longer on error
    
    async def force_recovery_check(self):
        """Force immediate recovery check"""
        # Import here to avoid circular imports
        from app.utils.health_monitor import health_monitor
        from app.client.broadcast_worker import broadcast_worker
        
        await broadcast_worker.check_and_fix_frozen_tasks()
        return await health_monitor.force_health_check()

# Global instance
recovery_manager = RecoveryManager()
